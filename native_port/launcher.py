"""Tk desktop launcher for the local Green Lantern port.

The launcher only stores its own preferences. Game saves, cache and runtime
data stay in the isolated profiles under .aster/runtime; graphics choices are
translated to command-line CVars and never written into the game profile.
"""
from __future__ import annotations

import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from games.green_lantern import GreenLantern
from . import graphics, settings
from .native_build import build_native, read_install
from .paths import project_root, python_command, external_env
from .diagnostics import diagnostics
from .errors import PortError
from .pipeline import prepare
from .sources import inspect_source
from .tasks import Cancellation
from .workspace import Workspace

PROJECT = project_root(__file__)
BG = '#0b1117'
PANEL = '#111a22'
CARD = '#16232c'
CARD_ALT = '#1b2d36'
LINE = '#263b43'
INK = '#e8f4f0'
MUTED = '#8fa6aa'
ACCENT = '#6ee7b7'
ACCENT_DARK = '#153f35'
WARN = '#ffcc66'
WARN_BG = '#2b2519'
DANGER = '#ff9b8f'
FONT = 'DejaVu Sans'
MONO = 'DejaVu Sans Mono'

MODE_FILES = {
    '30': ('.aster/build/rex-green/aster_green_lantern',
           '.aster/reports/rexglue-runtime-probe.json'),
    '60': ('.aster/build/rex-fps-validation-v9/aster_green_lantern',
           '.aster/reports/rexglue-runtime-probe-60fps.json'),
    'unlimited': ('.aster/build/rex-fps-unlimited-v10/aster_green_lantern',
                  '.aster/reports/rexglue-runtime-probe-unlimited.json'),
}
PROFILE_FILES = {
    '30': '.aster/runtime/green-lantern',
    '60': '.aster/runtime/green-lantern-60fps',
    'unlimited': '.aster/runtime/green-lantern-unlimited',
}
TARGET_TITLES = {
    '30': 'Jogar 30 fps',
    '60': 'Jogar 60 fps experimental',
    'unlimited': 'Jogar ilimitado experimental',
}
ANISO_LABELS = dict(graphics.ANISOTROPIC_LABELS)
ANISO_BY_LABEL = {label: value for value, label in ANISO_LABELS.items()}
TEXTURE_BY_LABEL = {label: value for value, label in graphics.TEXTURE_QUALITY_LABELS.items()}


class Launcher:
    def __init__(self, root):
        self.root = root
        root.title('Aster Native | Green Lantern')
        root.geometry('1160x720')
        root.minsize(1088, 696)
        root.configure(bg=BG)
        self.queue, self.events = queue.Queue(), []
        self.busy, self.cancel = False, Cancellation()
        self.last_result, self.last_environment = None, None
        self.selected_folder = None
        self.closed = False
        self.experimental_process = None
        self.experimental_lock = threading.Lock()
        self.settings_warning = None
        self._syncing = False
        self._vsync_preference = True
        try:
            cfg = settings.load(PROJECT)
        except PortError as exc:
            cfg, self.settings_warning = settings.defaults(PROJECT), exc.as_dict()
        self.cfg = cfg
        self.source = tk.StringVar(value=cfg['source'])
        self.workspace = tk.StringVar(value=cfg['workspace'])
        self.build_type = tk.StringVar(value=cfg['build_type'])
        self.jobs = tk.IntVar(value=cfg['jobs'])
        self.graphics_preset = tk.StringVar(value=cfg['graphics']['preset'])
        self.fps_target = tk.StringVar(value=cfg['graphics']['fps_target'])
        self.vsync = tk.BooleanVar(value=cfg['graphics']['vsync'])
        self.shader_mode = tk.StringVar(value=cfg['graphics']['shader_mode'])
        self.custom_render_scale = tk.IntVar(value=cfg['graphics']['render_scale'])
        self.custom_msaa = tk.BooleanVar(value=cfg['graphics']['msaa_2x'])
        self.custom_aniso = tk.StringVar(value=ANISO_LABELS.get(cfg['graphics']['anisotropic'],
                                                               ANISO_LABELS[3]))
        self.custom_texture = tk.StringVar(
            value=graphics.TEXTURE_QUALITY_LABELS.get(cfg['graphics']['texture_quality'], 'Padrão'))
        self.custom_dither = tk.BooleanVar(value=cfg['graphics']['present_dither'])
        self._vsync_preference = bool(cfg['graphics']['vsync'])
        self.status = tk.StringVar(value='Pronto para selecionar o dump e revisar as opções gráficas.')
        self.environment_status = tk.StringVar(value='Ambiente / diagnóstico não executado')
        self.source_status = tk.StringVar(value='Jogo / entrada ainda não validada')
        self.output_status = tk.StringVar(value='Artefato / compilação integral ainda não validada')
        self.engine_status = tk.StringVar(value='Build local: verificando…')
        self.graphics_summary = tk.StringVar(value='')
        self.warning_text = tk.StringVar(value='')
        self.quick_target = tk.StringVar(value='')
        self.quick_graphics = tk.StringVar(value='')
        self.quick_profile = tk.StringVar(value='')
        self.report_path = tk.StringVar(value='Relatórios ficam dentro do diretório de trabalho.')
        self.preset_buttons, self.target_buttons = {}, {}
        self._build_style()
        self._build_shell()
        self._set_graphics_vars(cfg['graphics'])
        self._refresh_graphics_ui()
        self._refresh_engine_status()
        self._refresh_play_state()
        self.status.set(self._idle_status())
        self.workspace.trace_add('write', lambda *_: self.refresh_paths())
        self.source.trace_add('write', lambda *_: self._refresh_play_state())
        for variable in (self.custom_render_scale, self.custom_msaa,
                         self.custom_aniso, self.custom_texture, self.custom_dither):
            variable.trace_add('write', lambda *_: self._on_custom_changed())
        self.fps_target.trace_add('write', lambda *_: self._on_target_changed())
        self.vsync.trace_add('write', lambda *_: self._on_vsync_changed())
        self.refresh_paths()
        if self.settings_warning:
            self.log({'task': 'Carregar configuração', 'error': self.settings_warning})
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.after_id = root.after(50, self.poll)

    # ------------------------------------------------------------------ style
    def _build_style(self):
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.', background=BG, foreground=INK, font=(FONT, 10))
        style.configure('TFrame', background=BG)
        style.configure('Card.TFrame', background=CARD)
        style.configure('Panel.TFrame', background=PANEL)
        style.configure('TLabel', background=BG, foreground=INK)
        style.configure('Card.TLabel', background=CARD, foreground=INK)
        style.configure('CardMuted.TLabel', background=CARD, foreground=MUTED)
        style.configure('Panel.TLabel', background=PANEL, foreground=MUTED)
        style.configure('Accent.TLabel', background=BG, foreground=ACCENT)
        style.configure('Warning.TLabel', background=CARD_ALT, foreground=WARN)
        style.configure('Title.TLabel', background=BG, foreground=INK, font=(FONT, 21, 'bold'))
        style.configure('H1.TLabel', background=CARD, foreground=INK, font=(FONT, 17, 'bold'))
        style.configure('H2.TLabel', background=CARD, foreground=INK, font=(FONT, 12, 'bold'))
        style.configure('Caps.TLabel', background=CARD, foreground=MUTED, font=(FONT, 8, 'bold'))
        style.configure('TButton', padding=(12, 8), background=CARD_ALT, foreground=INK,
                        borderwidth=0, focusthickness=0)
        style.map('TButton', background=[('active', '#29434d'), ('disabled', '#1b282e')],
                  foreground=[('disabled', '#6c8185')])
        style.configure('Accent.TButton', padding=(24, 16), background=ACCENT,
                        foreground='#06231a', font=(FONT, 12, 'bold'))
        style.map('Accent.TButton', background=[('active', '#8af0c7'), ('disabled', '#29473e')],
                  foreground=[('disabled', '#6c8b81')])
        style.configure('Secondary.TButton', padding=(14, 10), background=CARD_ALT, foreground=INK)
        style.map('Secondary.TButton', background=[('active', '#29434d'), ('disabled', '#1b282e')])
        style.configure('Ghost.TButton', padding=(10, 7), background=PANEL, foreground=MUTED)
        style.map('Ghost.TButton', background=[('active', '#1d3039')])
        style.configure('Danger.TButton', padding=(12, 8), background='#3a2224', foreground=DANGER)
        style.map('Danger.TButton',
                  background=[('active', '#4a2a2d'), ('disabled', '#26191b')],
                  foreground=[('disabled', '#725257')])
        style.configure('Preset.TButton', padding=(10, 11), background=CARD_ALT, foreground=INK,
                        font=(FONT, 9))
        style.map('Preset.TButton', background=[('active', '#29434d')])
        style.configure('PresetOn.TButton', padding=(10, 11), background=ACCENT_DARK,
                        foreground=ACCENT, font=(FONT, 9, 'bold'))
        style.map('PresetOn.TButton', background=[('active', '#1b5143')])
        style.configure('TNotebook', background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
        style.configure('TNotebook.Tab', padding=(18, 10), background=PANEL, foreground=MUTED,
                        font=(FONT, 10, 'bold'), borderwidth=0)
        style.map('TNotebook.Tab', background=[('selected', CARD), ('active', CARD_ALT)],
                  foreground=[('selected', ACCENT), ('active', INK)])
        style.configure('TEntry', fieldbackground=BG, foreground=INK, insertcolor=INK,
                        bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, padding=8)
        style.configure('TCombobox', fieldbackground=BG, foreground=INK, arrowcolor=MUTED,
                        bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, padding=6)
        style.map('TCombobox', fieldbackground=[('readonly', BG)], foreground=[('readonly', INK)])
        style.configure('TSpinbox', fieldbackground=BG, foreground=INK, arrowcolor=MUTED,
                        bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, padding=6)
        style.configure('TCheckbutton', background=CARD, foreground=INK, font=(FONT, 10))
        style.map('TCheckbutton', background=[('active', CARD)], foreground=[('disabled', MUTED)])
        style.configure('Treeview', background=BG, fieldbackground=BG, foreground=INK, rowheight=27,
                        borderwidth=0)
        style.configure('Treeview.Heading', background=PANEL, foreground=MUTED,
                        font=(FONT, 9, 'bold'))
        style.configure('Horizontal.TProgressbar', background=ACCENT, troughcolor=CARD_ALT,
                        bordercolor=CARD_ALT, lightcolor=ACCENT, darkcolor=ACCENT)

    def _card(self, parent, **pack_options):
        card = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        card.pack(**pack_options)
        return card

    def _caps(self, parent, text, bg=CARD):
        return tk.Label(parent, text=text.upper(), bg=bg, fg=MUTED,
                        font=(FONT, 8, 'bold'), anchor='w')

    # ------------------------------------------------------------------- shell
    def _build_shell(self):
        shell = tk.Frame(self.root, bg=BG, padx=22, pady=12)
        shell.pack(fill='both', expand=True)
        header = tk.Frame(shell, bg=BG)
        header.pack(fill='x', pady=(0, 8))
        brand = tk.Frame(header, bg=BG)
        brand.pack(side='left', fill='x', expand=True)
        tk.Label(brand, text='ASTER', bg=BG, fg=ACCENT,
                 font=(FONT, 22, 'bold')).pack(side='left')
        tk.Label(brand, text='  NATIVE  /  GREEN LANTERN', bg=BG, fg=MUTED,
                 font=(FONT, 9, 'bold')).pack(side='left', padx=(10, 0), pady=(8, 0))
        tk.Label(brand, text='Port local para PC · ' + ('D3D12 / ROV' if sys.platform == 'win32' else 'FSI / Vulkan'), bg=BG, fg=MUTED,
                 font=(FONT, 9)).pack(side='left', padx=(20, 0), pady=(8, 0))
        badge = tk.Label(header, text='AMBIENTE LOCAL  •  EM VALIDAÇÃO', bg=ACCENT_DARK,
                         fg=ACCENT, font=(FONT, 8, 'bold'), padx=12, pady=7)
        badge.pack(side='right')
        tk.Frame(shell, bg=LINE, height=1).pack(fill='x', pady=(0, 6))
        self.tabs = ttk.Notebook(shell)
        self.tabs.pack(fill='both', expand=True)
        self.play_tab = tk.Frame(self.tabs, bg=BG, padx=12, pady=14)
        self.graphics_tab = tk.Frame(self.tabs, bg=BG, padx=12, pady=14)
        self.game_tab = tk.Frame(self.tabs, bg=BG, padx=12, pady=14)
        self.diag_tab = tk.Frame(self.tabs, bg=BG, padx=12, pady=14)
        self.tabs.add(self.play_tab, text='Jogar')
        self.tabs.add(self.graphics_tab, text='Gráficos')
        self.tabs.add(self.game_tab, text='Jogo e arquivos')
        self.tabs.add(self.diag_tab, text='Diagnóstico')
        self._build_play_tab()
        self._build_graphics_tab()
        self._build_game_tab()
        self._build_diag_tab()
        footer = tk.Frame(shell, bg=BG)
        footer.pack(fill='x', pady=(4, 0))
        self.status_bar = tk.Label(footer, textvariable=self.status, bg=PANEL, fg=MUTED,
                                   anchor='w', justify='left', padx=12, pady=8,
                                   font=(FONT, 9), wraplength=800)
        self.status_bar.pack(side='left', fill='x', expand=True)
        tk.Label(footer, text=str(PROJECT / '.aster/config/settings.json'), bg=BG, fg='#5d7378',
                 font=(MONO, 8), padx=8).pack(side='right')
        self.widgets = [self.folder_button, self.select_button, self.inspect_button,
                        self.prepare_button, self.cancel_button, self.compile_button,
                        self.stop_experimental_button, self.open_profile_button, self.play_button,
                        self.source_entry, self.work_entry, self.jobs_spin, self.save_button,
                        self.doctor_button, self.clear_button, self.export_button,
                        self.copy_button, self.restore_graphics_button]
        self._readonly_widgets = [self.build_combo, self.shader_combo]

    # -------------------------------------------------------------- play tab
    def _build_play_tab(self):
        hero = self._card(self.play_tab, fill='x')
        hero_left = tk.Frame(hero, bg=CARD)
        hero_left.pack(side='left', fill='both', expand=True, padx=20, pady=17)
        self._caps(hero_left, 'Xbox 360 · Port nativo experimental').pack(anchor='w')
        tk.Label(hero_left, text='Green Lantern: Rise of the Manhunters', bg=CARD, fg=INK,
                 font=(FONT, 18, 'bold')).pack(anchor='w', pady=(5, 2))
        tk.Label(hero_left, text='Escolha o alvo, selecione o dump e abra a sessão. '
                  'A configuração gráfica é aplicada por CVars e não toca no save do jogo.',
                 bg=CARD, fg=MUTED, font=(FONT, 9), wraplength=640,
                 justify='left').pack(anchor='w')
        hero_right = tk.Frame(hero, bg=CARD)
        hero_right.pack(side='right', padx=20, pady=16)
        self.play_button = ttk.Button(hero_right, text='JOGAR AGORA', style='Accent.TButton',
                                      command=self.play)
        self.play_button.pack(fill='x')
        tk.Label(hero_right, textvariable=self.quick_target, bg=CARD, fg=ACCENT,
                 font=(FONT, 9, 'bold')).pack(anchor='e', pady=(7, 0))
        self.launch_button = self.play_button
        self.experimental_button = self.play_button

        chips = tk.Frame(self.play_tab, bg=BG)
        chips.pack(fill='x', pady=(10, 0))
        for index, (caption, variable) in enumerate((
                ('ALVO DE QUADROS', self.quick_target),
                ('PRESET GRÁFICO', self.quick_graphics),
                ('PERFIL DE SESSÃO', self.quick_profile))):
            chips.columnconfigure(index, weight=1, uniform='chip')
            card = tk.Frame(chips, bg=CARD, highlightthickness=1, highlightbackground=LINE)
            card.grid(row=0, column=index, sticky='nsew', padx=(0 if index == 0 else 5, 0))
            tk.Label(card, text=caption, bg=CARD, fg=MUTED, font=(FONT, 8, 'bold'),
                     anchor='w').pack(fill='x', padx=12, pady=(9, 0))
            tk.Label(card, textvariable=variable, bg=CARD, fg=INK, font=(FONT, 10, 'bold'),
                     anchor='w', wraplength=300, justify='left').pack(fill='x', padx=12, pady=(2, 9))

        self.warning_frame = tk.Frame(self.play_tab, bg=WARN_BG,
                                      highlightthickness=1, highlightbackground='#5c4b24')
        self.warning_label = tk.Label(self.warning_frame, textvariable=self.warning_text,
                                      bg=WARN_BG, fg=WARN, font=(FONT, 9), anchor='w',
                                      justify='left', wraplength=1020, padx=12, pady=8)
        self.warning_label.pack(fill='x')

        source_card = self.source_card = self._card(self.play_tab, fill='x', pady=(10, 0))
        heading = tk.Frame(source_card, bg=CARD)
        heading.pack(fill='x', padx=16, pady=(13, 0))
        self._caps(heading, 'Pasta do jogo').pack(side='left')
        tk.Label(heading, textvariable=self.engine_status, bg=CARD, fg=MUTED,
                 font=(FONT, 8)).pack(side='right')
        row = tk.Frame(source_card, bg=CARD)
        row.pack(fill='x', padx=16, pady=(6, 0))
        self.source_entry = ttk.Entry(row, textvariable=self.source)
        self.source_entry.pack(side='left', fill='x', expand=True)
        self.folder_button = ttk.Button(row, text='Selecionar pasta…', style='Secondary.TButton',
                                        command=self.select_folder)
        self.folder_button.pack(side='left', padx=(8, 0))
        self.select_button = ttk.Button(row, text='ISO / XEX…', style='Ghost.TButton',
                                        command=self.select)
        self.select_button.pack(side='left', padx=(5, 0))
        actions = tk.Frame(source_card, bg=CARD)
        actions.pack(fill='x', padx=16, pady=(8, 13))
        self.inspect_button = ttk.Button(actions, text='Inspecionar dump', style='Secondary.TButton',
                                         command=self.inspect)
        self.inspect_button.pack(side='left')
        self.prepare_button = ttk.Button(actions, text='Preparar evidências', style='Ghost.TButton',
                                         command=self.prepare)
        self.prepare_button.pack(side='left', padx=(6, 0))
        self.stop_experimental_button = ttk.Button(actions, text='Encerrar sessão',
                                                   style='Danger.TButton', state='disabled',
                                                   command=self.stop_experimental)
        self.stop_experimental_button.pack(side='right')
        self.open_profile_button = ttk.Button(actions, text='Abrir perfil', style='Ghost.TButton',
                                              command=self.open_profile)
        self.open_profile_button.pack(side='right', padx=(0, 6))
        self.cancel_button = ttk.Button(actions, text='Cancelar tarefa', style='Ghost.TButton',
                                        state='disabled', command=self.stop_experimental)
        self.cancel_button.pack(side='right', padx=(0, 6))
        self.progress = ttk.Progressbar(source_card, mode='determinate', value=0)
        self.progress.pack(fill='x', padx=16, pady=(0, 12))

        notes = tk.Frame(self.play_tab, bg=BG)
        notes.pack(fill='x', pady=(10, 0))
        notes_data = (
            ('Saves separados',
             'Cada alvo usa seu próprio perfil em .aster/runtime. O launcher só grava preferências '
             'locais e nunca edita o save do jogo.'),
            ('Validação antes de abrir',
             'O launcher confere dump, build, plugin e referência FSI com --validar antes de abrir '
             'a sessão.'),
            ('Experimental é opt-in',
             '30 fps é o padrão. 60 e ilimitado pedem confirmação e usam builds e perfis isolados.'),
        )
        for index, (title, body) in enumerate(notes_data):
            notes.columnconfigure(index, weight=1, uniform='note')
            card = tk.Frame(notes, bg=CARD_ALT, highlightthickness=1,
                            highlightbackground='#30464f')
            card.grid(row=0, column=index, sticky='nsew', padx=(0 if index == 0 else 7, 0))
            tk.Label(card, text=title, bg=CARD_ALT, fg=ACCENT, font=(FONT, 9, 'bold'),
                     anchor='w').pack(fill='x', padx=12, pady=(9, 1))
            tk.Label(card, text=body, bg=CARD_ALT, fg=MUTED, font=(FONT, 8), anchor='w',
                     justify='left', wraplength=280).pack(fill='x', padx=10, pady=(0, 9))

    # ---------------------------------------------------------- graphics tab
    def _build_graphics_tab(self):
        top = tk.Frame(self.graphics_tab, bg=BG)
        top.pack(fill='x')
        tk.Label(top, text='Qualidade visual', bg=BG, fg=INK,
                 font=(FONT, 17, 'bold')).pack(side='left')
        self.restore_graphics_button = ttk.Button(top, text='Restaurar padrão', style='Ghost.TButton',
                                                  command=self.restore_graphics)
        self.restore_graphics_button.pack(side='right')
        tk.Label(self.graphics_tab, text='Presets alteram resolução interna, MSAA, filtragem e memória '
                  'de texturas. O alvo de FPS é aplicado à sessão; 60 e ilimitado são experimentais.',
                 bg=BG, fg=MUTED, font=(FONT, 9), wraplength=1050,
                 justify='left').pack(anchor='w', pady=(4, 10))
        preset_frame = tk.Frame(self.graphics_tab, bg=BG)
        preset_frame.pack(fill='x')
        preset_text = {
            'low': 'BAIXA\n720p · leve',
            'default': 'PADRÃO\n720p · equilíbrio',
            'high': 'ALTA\n1440p · nítido',
            'ultra': 'ULTRA\n2160p · máximo',
            'custom': 'PERSONALIZADA\najuste fino',
        }
        for index, name in enumerate(graphics.PRESETS):
            preset_frame.columnconfigure(index, weight=1, uniform='preset')
            button = ttk.Button(preset_frame, text=preset_text[name], style='Preset.TButton',
                                command=lambda n=name: self.choose_preset(n))
            button.grid(row=0, column=index, sticky='nsew', padx=(0 if index == 0 else 5, 0))
            self.preset_buttons[name] = button

        target_head = tk.Frame(self.graphics_tab, bg=BG)
        target_head.pack(fill='x', pady=(14, 0))
        tk.Label(target_head, text='Alvo de quadros', bg=BG, fg=INK,
                 font=(FONT, 13, 'bold')).pack(side='left')
        tk.Label(target_head, text='30 fps é o padrão; 60 e ilimitado exigem opt-in.',
                 bg=BG, fg=MUTED, font=(FONT, 9)).pack(side='left', padx=(12, 0), pady=(4, 0))
        target_frame = tk.Frame(self.graphics_tab, bg=BG)
        target_frame.pack(fill='x', pady=(6, 0))
        target_text = {'30': '30 fps\npadrão', '60': '60 fps\nexperimental',
                       'unlimited': 'ILIMITADO\nexperimental'}
        for index, target in enumerate(graphics.TARGETS):
            target_frame.columnconfigure(index, weight=1, uniform='target')
            button = ttk.Button(target_frame, text=target_text[target], style='Preset.TButton',
                                command=lambda t=target: self.choose_target(t))
            button.grid(row=0, column=index, sticky='nsew', padx=(0 if index == 0 else 5, 0))
            self.target_buttons[target] = button

        self.target_note = tk.Label(self.graphics_tab, text='', bg=BG, fg=MUTED,
                                    font=(FONT, 9), wraplength=1050, justify='left')
        self.target_note.pack(anchor='w', pady=(7, 0))
        options = self._card(self.graphics_tab, fill='x', pady=(12, 0))
        options_left = tk.Frame(options, bg=CARD)
        options_left.pack(side='left', fill='both', expand=True, padx=16, pady=13)
        self._caps(options_left, 'Sessão').pack(anchor='w')
        self.vsync_check = ttk.Checkbutton(options_left, text='VSync', variable=self.vsync)
        self.vsync_check.pack(anchor='w', pady=(8, 0))
        shader_row = tk.Frame(options_left, bg=CARD)
        shader_row.pack(fill='x', pady=(8, 0))
        tk.Label(shader_row, text='Shaders novos', bg=CARD, fg=MUTED,
                 font=(FONT, 9)).pack(side='left')
        self.shader_combo = ttk.Combobox(shader_row, textvariable=self.shader_mode,
                                         values=graphics.SHADER_MODES, state='readonly', width=10)
        self.shader_combo.pack(side='left', padx=(8, 0))
        tk.Label(options_left, text='async evita travar na compilação; blocking espera o shader. '
                  'O cache de shaders é preservado.', bg=CARD, fg=MUTED, font=(FONT, 8),
                 wraplength=390, justify='left').pack(anchor='w', pady=(9, 0))
        options_right = tk.Frame(options, bg=CARD)
        options_right.pack(side='right', fill='both', expand=True, padx=16, pady=13)
        self._caps(options_right, 'Ajustes personalizados').pack(anchor='w')
        self.custom_grid = tk.Frame(options_right, bg=CARD)
        self.custom_grid.pack(fill='x', pady=(8, 0))
        tk.Label(self.custom_grid, text='Resolução interna', bg=CARD, fg=MUTED,
                 font=(FONT, 9)).grid(row=0, column=0, sticky='w', pady=3)
        self.render_scale_spin = ttk.Spinbox(self.custom_grid, from_=1, to=3, width=4,
                                             textvariable=self.custom_render_scale)
        self.render_scale_spin.grid(row=0, column=1, sticky='w', padx=(10, 18))
        tk.Label(self.custom_grid, text='MSAA do jogo', bg=CARD, fg=MUTED,
                 font=(FONT, 9)).grid(row=0, column=2, sticky='w', pady=3)
        self.msaa_check = ttk.Checkbutton(self.custom_grid, variable=self.custom_msaa)
        self.msaa_check.grid(row=0, column=3, sticky='w', padx=(10, 0))
        tk.Label(self.custom_grid, text='Anisotrópico', bg=CARD, fg=MUTED,
                 font=(FONT, 9)).grid(row=1, column=0, sticky='w', pady=3)
        self.aniso_combo = ttk.Combobox(self.custom_grid, textvariable=self.custom_aniso,
                                        values=list(ANISO_LABELS.values()), state='readonly', width=17)
        self.aniso_combo.grid(row=1, column=1, sticky='w', padx=(10, 18))
        tk.Label(self.custom_grid, text='Cache de texturas', bg=CARD, fg=MUTED,
                 font=(FONT, 9)).grid(row=1, column=2, sticky='w', pady=3)
        self.texture_combo = ttk.Combobox(self.custom_grid, textvariable=self.custom_texture,
                                          values=list(graphics.TEXTURE_QUALITY_LABELS.values()),
                                          state='readonly', width=12)
        self.texture_combo.grid(row=1, column=3, sticky='w', padx=(10, 0))
        self.dither_check = ttk.Checkbutton(self.custom_grid, text='Dithering',
                                            variable=self.custom_dither)
        self.dither_check.grid(row=2, column=0, columnspan=2, sticky='w', pady=(5, 0))
        tk.Label(options_right, text='Mudar um valor ativa o preset Personalizada automaticamente.',
                 bg=CARD, fg=MUTED, font=(FONT, 8), wraplength=440,
                 justify='left').pack(anchor='w', pady=(8, 0))
        self.graphics_summary_label = tk.Label(self.graphics_tab, textvariable=self.graphics_summary,
                                               bg=BG, fg=ACCENT, font=(FONT, 9),
                                               wraplength=1050, justify='left')
        self.graphics_summary_label.pack(anchor='w', pady=(10, 0))

    # --------------------------------------------------------------- game tab
    def _build_game_tab(self):
        tk.Label(self.game_tab, text='Jogo e arquivos', bg=BG, fg=INK,
                 font=(FONT, 17, 'bold')).pack(anchor='w')
        tk.Label(self.game_tab, text='O dump precisa conter default.xex. A pasta de trabalho e os '
                  'perfis ficam em .aster, separados dos arquivos originais.',
                 bg=BG, fg=MUTED, font=(FONT, 9), wraplength=1050,
                 justify='left').pack(anchor='w', pady=(4, 10))
        workspace_card = self._card(self.game_tab, fill='x')
        left = tk.Frame(workspace_card, bg=CARD)
        left.pack(fill='x', padx=16, pady=13)
        self._caps(left, 'Diretório de trabalho').pack(anchor='w')
        work_row = tk.Frame(left, bg=CARD)
        work_row.pack(fill='x', pady=(6, 0))
        self.work_entry = ttk.Entry(work_row, textvariable=self.workspace)
        self.work_entry.pack(side='left', fill='x', expand=True)
        self.work_button = ttk.Button(work_row, text='Escolher…', style='Ghost.TButton',
                                      command=self.select_workspace)
        self.work_button.pack(side='left', padx=(8, 0))
        self.paths_label = tk.Label(left, text='', bg=CARD, fg=MUTED, font=(FONT, 8),
                                    wraplength=1000, justify='left')
        self.paths_label.pack(anchor='w', pady=(6, 0))
        config_row = tk.Frame(left, bg=CARD)
        config_row.pack(fill='x', pady=(9, 0))
        tk.Label(config_row, text='Build', bg=CARD, fg=MUTED, font=(FONT, 9)).pack(side='left')
        self.build_combo = ttk.Combobox(config_row, textvariable=self.build_type, state='readonly',
                                        width=15, values=('Release', 'Debug', 'RelWithDebInfo'))
        self.build_combo.pack(side='left', padx=(8, 18))
        tk.Label(config_row, text='Tarefas paralelas', bg=CARD, fg=MUTED,
                 font=(FONT, 9)).pack(side='left')
        self.jobs_spin = ttk.Spinbox(config_row, from_=1, to=64, textvariable=self.jobs, width=5)
        self.jobs_spin.pack(side='left', padx=(8, 18))
        self.save_button = ttk.Button(config_row, text='Salvar preferências', style='Secondary.TButton',
                                      command=self.save_settings)
        self.save_button.pack(side='left')
        tk.Label(left, text='Gerar port valida a revisão do dump, gera C++ e compila localmente. '
                  'Requer CMake, Ninja e Clang/C++23 (Build Tools + Windows SDK no Windows).', bg=CARD, fg=MUTED,
                 font=(FONT, 8)).pack(anchor='w', pady=(6, 0))
        actions = tk.Frame(self.game_tab, bg=BG)
        actions.pack(fill='x', pady=(10, 0))
        self.compile_button = ttk.Button(actions, text='Gerar port nativo', style='Secondary.TButton',
                                         command=self.generate_native, state='disabled')
        self.compile_button.pack(side='left')
        self.doctor_button = ttk.Button(actions, text='Verificar ambiente', style='Secondary.TButton',
                                        command=self.doctor)
        self.doctor_button.pack(side='left', padx=(6, 0))
        self.clear_button = ttk.Button(actions, text='Limpar cache…', style='Ghost.TButton',
                                       command=self.clear_cache)
        self.clear_button.pack(side='left', padx=(6, 0))
        self.summary = tk.Text(self.game_tab, height=4, bg=BG, fg=INK, relief='flat',
                               wrap='word', padx=12, pady=12, font=(FONT, 9),
                               highlightthickness=1, highlightbackground=LINE)
        self.summary.pack(fill='both', expand=True, pady=(10, 0))
        self.set_summary('Nenhuma entrada validada.\n\nSelecione a pasta que contém default.xex e os '
                         'assets extraídos do jogo. O inventário é local e não modifica o dump.\n\n'
                         'Para jogar, o host local e a referência FSI precisam existir; o launcher '
                         'executa --validar antes de abrir a sessão. O modo 30 fps usa o perfil '
                         'principal. Os modos 60 fps e ilimitado usam perfis isolados.')
        self.requirements = tk.Frame(self.game_tab, bg=CARD_ALT, highlightthickness=1,
                                     highlightbackground='#3a4f57')
        self.requirements.pack(fill='x', pady=(10, 0))
        tk.Label(self.requirements, text='Para outro computador com o mesmo dump', bg=CARD_ALT,
                 fg=ACCENT, font=(FONT, 9, 'bold'), anchor='w').pack(fill='x', padx=12, pady=(8, 1))
        tk.Label(self.requirements, text='1. Confirme o SHA-256 do default.xex.  2. Compile o host '
                 'local e o plugin xenos.  3. Gere/valide o probe FSI.  4. Selecione o dump aqui: '
                 'nada do jogo é escrito fora do perfil isolado.', bg=CARD_ALT, fg=MUTED,
                 font=(FONT, 8), anchor='w', justify='left', wraplength=1030).pack(fill='x', padx=12,
                                                                                  pady=(0, 8))

    # -------------------------------------------------------------- diag tab
    def _build_diag_tab(self):
        top = tk.Frame(self.diag_tab, bg=BG)
        top.pack(fill='x')
        tk.Label(top, text='Diagnóstico', bg=BG, fg=INK,
                 font=(FONT, 17, 'bold')).pack(side='left')
        self.environment_status_label = tk.Label(top, textvariable=self.environment_status,
                                                 bg=BG, fg=MUTED, font=(FONT, 9))
        self.environment_status_label.pack(side='right', pady=(5, 0))
        env_card = self._card(self.diag_tab, fill='x', pady=(8, 0))
        self.environment = tk.Text(env_card, bg=BG, fg=INK, relief='flat', height=2, wrap='word',
                                   padx=10, pady=8, font=(MONO, 9), highlightthickness=0)
        self.environment.pack(fill='x', padx=10, pady=8)
        self.environment.insert('end', 'Execute “Verificar ambiente” para consultar ferramentas e versões locais.')
        self.environment.configure(state='disabled')
        task_card = self._card(self.diag_tab, fill='x', pady=(10, 0))
        self.task_tree = ttk.Treeview(task_card, columns=('state', 'duration'),
                                      show='tree headings', height=5)
        self.task_tree.heading('#0', text='Tarefa')
        self.task_tree.heading('state', text='Estado')
        self.task_tree.heading('duration', text='Duração')
        self.task_tree.column('#0', width=500)
        self.task_tree.column('state', width=130)
        self.task_tree.column('duration', width=100)
        self.task_tree.pack(fill='x', padx=10, pady=10)
        self.logs = tk.Text(self.diag_tab, bg=BG, fg=INK, insertbackground=INK, relief='flat',
                            wrap='word', font=(MONO, 8), height=8,
                            highlightthickness=1, highlightbackground=LINE)
        self.logs.pack(fill='both', expand=True, pady=(10, 0))
        self.logs.configure(state='disabled')
        actions = tk.Frame(self.diag_tab, bg=BG)
        actions.pack(fill='x', pady=(10, 0))
        self.export_button = ttk.Button(actions, text='Salvar diagnóstico e logs', style='Secondary.TButton',
                                        command=self.export_report)
        self.export_button.pack(side='left')
        self.copy_button = ttk.Button(actions, text='Copiar logs', style='Ghost.TButton',
                                      command=self.copy_logs)
        self.copy_button.pack(side='left', padx=(6, 0))
        tk.Label(self.diag_tab, textvariable=self.report_path, bg=BG, fg=MUTED,
                 font=(FONT, 8), wraplength=1000, justify='left').pack(anchor='w', pady=(7, 0))

    # ---------------------------------------------------------- graphics sync
    def _set_graphics_vars(self, data):
        self._syncing = True
        try:
            self.graphics_preset.set(data['preset'])
            self.fps_target.set(data['fps_target'])
            self.vsync.set(data['vsync'])
            self.shader_mode.set(data['shader_mode'])
            self.custom_render_scale.set(data['render_scale'])
            self.custom_msaa.set(data['msaa_2x'])
            self.custom_aniso.set(ANISO_LABELS.get(data['anisotropic'], ANISO_LABELS[3]))
            self.custom_texture.set(graphics.TEXTURE_QUALITY_LABELS.get(
                data['texture_quality'], graphics.TEXTURE_QUALITY_LABELS['default']))
            self.custom_dither.set(data['present_dither'])
            if data['fps_target'] != 'unlimited':
                self._vsync_preference = bool(data['vsync'])
        finally:
            self._syncing = False

    def _graphics_data(self):
        target = self.fps_target.get()
        preset = self.graphics_preset.get()
        common = dict(fps_target=target, vsync=self.vsync.get(),
                      shader_mode=self.shader_mode.get())
        if preset == 'custom':
            return graphics.from_options(
                'custom',
                render_scale=self.custom_render_scale.get(),
                msaa_2x=self.custom_msaa.get(),
                anisotropic=ANISO_BY_LABEL.get(self.custom_aniso.get(), 3),
                texture_quality=TEXTURE_BY_LABEL.get(self.custom_texture.get(), 'default'),
                present_dither=self.custom_dither.get(),
                **common)
        return graphics.from_options(preset, **common)

    def _refresh_graphics_ui(self):
        try:
            data = self._graphics_data()
            text = graphics.summary(data)
        except (PortError, tk.TclError) as exc:
            data, text = None, str(exc)
        self.graphics_summary.set(text)
        target = self.fps_target.get()
        preset = self.graphics_preset.get()
        if data:
            self.quick_target.set(graphics.TARGET_LABELS[target] +
                                  (' · experimental' if target != '30' else ' · padrão'))
            self.quick_graphics.set(
                f"{graphics.PRESET_LABELS[preset]} · {graphics.internal_resolution(data['render_scale'])}")
            self.quick_profile.set({
                '30': '30 fps · perfil principal',
                '60': '60 fps · perfil isolado',
                'unlimited': 'ilimitado · perfil isolado',
            }[target])
        for name, button in self.preset_buttons.items():
            button.configure(style='PresetOn.TButton' if name == preset else 'Preset.TButton')
        for target_name, button in self.target_buttons.items():
            button.configure(style='PresetOn.TButton' if target_name == target else 'Preset.TButton')
        self.warning_frame.pack_forget()
        if target == '60':
            self.warning_text.set('MODO 60 FPS EXPERIMENTAL · usa o port local e um perfil isolado. '
                                  'O timestep foi medido, mas combate, física, animações, áudio e '
                                  'campanha completa ainda não estão certificados.')
            self.warning_frame.pack(fill='x', pady=(10, 0), before=self.source_card)
        elif target == 'unlimited':
            self.warning_text.set('MODO ILIMITADO EXPERIMENTAL · remove a espera de pacing, desliga '
                                  'VSync e usa apresentação imediata. Pode causar tearing, alto uso de '
                                  'GPU e velocidade incorreta; use apenas para testar.')
            self.warning_frame.pack(fill='x', pady=(10, 0), before=self.source_card)
        note = graphics.TARGET_DESCRIPTIONS[target]
        if target == 'unlimited':
            note += ' VSync fica desligado e o perfil é separado.'
        self.target_note.configure(text=note, fg=WARN if target != '30' else MUTED)
        self._refresh_custom_state()
        self._refresh_engine_status()

    def _refresh_custom_state(self):
        state = 'disabled' if self.busy else 'normal'
        for widget in (self.render_scale_spin, self.msaa_check, self.aniso_combo,
                       self.texture_combo, self.dither_check):
            widget.configure(state=state)
        self.msaa_check.configure(state='disabled')
        if not self.busy:
            self.aniso_combo.configure(state='readonly')
            self.texture_combo.configure(state='readonly')
        if self.fps_target.get() == 'unlimited' or self.busy:
            self.vsync_check.configure(state='disabled')
        else:
            self.vsync_check.configure(state='normal')
        if self.busy:
            self.shader_combo.configure(state='disabled')
        else:
            self.shader_combo.configure(state='readonly')

    def _on_custom_changed(self):
        if self._syncing or self.busy:
            return
        if self.graphics_preset.get() != 'custom':
            self._syncing = True
            try:
                self.graphics_preset.set('custom')
            finally:
                self._syncing = False
        self._refresh_graphics_ui()

    def _on_target_changed(self):
        if self._syncing:
            return
        target = self.fps_target.get()
        if target == 'unlimited':
            if self.vsync.get():
                self._syncing = True
                try:
                    self._vsync_preference = True
                    self.vsync.set(False)
                finally:
                    self._syncing = False
        else:
            if not self.vsync.get() and self._vsync_preference:
                self._syncing = True
                try:
                    self.vsync.set(True)
                finally:
                    self._syncing = False
        self._refresh_graphics_ui()

    def _on_vsync_changed(self):
        if self._syncing:
            return
        if self.fps_target.get() != 'unlimited':
            self._vsync_preference = bool(self.vsync.get())
        self._refresh_graphics_ui()

    def choose_preset(self, name):
        if self.busy:
            return
        try:
            data = graphics.apply_preset(name, self._graphics_data())
        except PortError as exc:
            self.status.set(str(exc))
            return
        self._set_graphics_vars(data)
        self._refresh_graphics_ui()
        self.status.set(f'Preset {graphics.PRESET_LABELS[name]} selecionado para a próxima sessão.')

    def choose_target(self, target):
        if self.busy:
            return
        old = self.fps_target.get()
        self.fps_target.set(target)
        if target == 'unlimited':
            self.vsync.set(False)
        self._refresh_graphics_ui()
        if old != target:
            self.status.set(f'Alvo alterado para {graphics.TARGET_LABELS[target]}. '
                            'As opções só valem para a próxima sessão.')

    def restore_graphics(self):
        if self.busy:
            return
        self._set_graphics_vars(graphics.defaults())
        self._refresh_graphics_ui()
        self.status.set('Opções gráficas restauradas para o padrão de 30 fps.')

    # ------------------------------------------------------------- state/UI
    def _source_ready(self):
        try:
            folder = Path(self.source.get()).expanduser()
        except (OSError, ValueError):
            return False
        return bool(self.source.get()) and folder.is_dir() and (folder / 'default.xex').is_file()

    def _engine_paths(self, target=None):
        target = target or self.fps_target.get()
        try:
            installation = read_install(PROJECT)
        except PortError:
            installation = None
        if installation:
            return PROJECT / installation['binary'], PROJECT / '.aster/config/native-install.json'
        binary, report = MODE_FILES[target]
        return PROJECT / binary, PROJECT / report

    def _engine_ready(self, target=None):
        binary, report = self._engine_paths(target)
        return binary.is_file() and report.is_file()

    def _refresh_engine_status(self):
        target = self.fps_target.get()
        binary, report = self._engine_paths(target)
        if binary.is_file() and report.is_file():
            self.engine_status.set('Build e referência locais encontrados')
        elif binary.is_file():
            self.engine_status.set('Build encontrado; falta o probe FSI de referência')
        else:
            self.engine_status.set('Build local ausente para esta opção')
        self._refresh_play_state()

    def _refresh_play_state(self):
        if self.busy:
            return
        ready = self._source_ready() and self._engine_ready()
        self.play_button.configure(state='normal' if self._source_ready() else 'disabled',
                                   text='JOGAR AGORA' if ready else 'GERAR PORT NATIVO')
        self.compile_button.configure(state='normal' if self._source_ready() else 'disabled')

    def _idle_status(self):
        if not self.source.get():
            return 'Selecione a pasta do jogo para começar.'
        if not self._source_ready():
            return 'A pasta selecionada precisa conter default.xex.'
        if not self._engine_ready():
            target = graphics.TARGET_LABELS[self.fps_target.get()]
            return f'Build ou referência FSI ausente para {target}; consulte Jogo e arquivos.'
        target = graphics.TARGET_LABELS[self.fps_target.get()]
        preset = graphics.PRESET_LABELS[self.graphics_preset.get()]
        return f'Pronto para abrir {target} com preset {preset}.'

    def _set_busy_controls(self, enabled):
        for widget in self.widgets:
            try:
                widget.configure(state='normal' if enabled else 'disabled')
            except tk.TclError:
                pass
        for button in list(self.preset_buttons.values()) + list(self.target_buttons.values()):
            button.configure(state='normal' if enabled else 'disabled')
        for widget in self._readonly_widgets:
            widget.configure(state='readonly' if enabled else 'disabled')
        self.compile_button.configure(state='normal' if enabled and self._source_ready() else 'disabled')
        self.cancel_button.configure(state='disabled' if enabled else 'normal')
        self.stop_experimental_button.configure(
            state='normal' if (not enabled and self.experimental_process is not None) else 'disabled')
        self._refresh_custom_state()

    # --------------------------------------------------------------- actions
    def refresh_paths(self):
        try:
            work = Workspace(self.workspace.get(), PROJECT)
            self.paths_label.configure(text=f'Saída: {work.path("output")}\n'
                                            f'Cache: {work.path("cache/v1")}')
        except PortError as exc:
            self.paths_label.configure(text=str(exc))

    def config(self):
        try:
            return settings.validate({'schema': 2, 'workspace': self.workspace.get(),
                                      'source': self.source.get(), 'build_type': self.build_type.get(),
                                      'jobs': self.jobs.get(), 'graphics': self._graphics_data()}, PROJECT)
        except tk.TclError as exc:
            raise PortError('SETTINGS_VALUE', 'Número de tarefas inválido.') from exc

    def save_settings(self, quiet=False):
        try:
            p = settings.save(self.config(), PROJECT)
            if not quiet:
                self.log({'task': 'Salvar preferências', 'state': 'completed', 'path': str(p)})
                self.status.set('Preferências salvas localmente • o save do jogo não foi alterado')
            return True
        except (PortError, OSError) as exc:
            self.status.set(str(exc))
            if not quiet:
                messagebox.showerror('Configuração inválida', str(exc))
            return False

    def close(self):
        if self.closed:
            return
        self.save_settings(quiet=True)
        with self.experimental_lock:
            self.closed = True
        self.cancel.cancel()
        self.stop_experimental()
        self.progress.stop()
        try:
            self.root.after_cancel(self.after_id)
        except tk.TclError:
            pass
        self.root.destroy()

    def stop_experimental(self):
        """Stop only the child started by this launcher; never search global PIDs."""
        self.cancel.cancel()
        with self.experimental_lock:
            process = self.experimental_process
        if process is None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return

        def stop():
            try:
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            except ProcessLookupError:
                pass

        threading.Thread(target=stop, daemon=False).start()

    def _confirm_target(self, target):
        if target == '30':
            return True
        if target == '60':
            title = '60 fps experimental'
            text = ('O modo 60 fps é experimental.\n\n'
                    'O passo de simulação foi medido em par com 30 fps, mas combate, física, '
                    'animações, áudio e campanha completa não estão certificados.\n\n'
                    'Usa o port local e um perfil isolado; não altera o save de 30 fps.\n\n'
                    'Deseja abrir mesmo assim?')
        else:
            title = 'FPS ilimitado experimental'
            text = ('O modo ilimitado é experimental e remove a espera de pacing do motor.\n\n'
                    'Ele desliga o VSync, usa apresentação imediata e pode causar tearing, alto '
                    'consumo de GPU e velocidade de simulação incorreta.\n\n'
                    'Usa um perfil isolado; não altera o save de 30 fps.\n\n'
                    'Deseja abrir mesmo assim?')
        return messagebox.askyesno(title, text)

    def play_command(self, folder=None):
        folder = Path(folder or self.source.get()).expanduser().resolve()
        data = self._graphics_data()
        command = python_command(PROJECT / 'scripts/play_green_lantern.py') + [
                   '--shader-mode', data['shader_mode'],
                   '--vsync', 'on' if data['vsync'] else 'off',
                   '--fps-target', data['fps_target'],
                   '--graphics-preset', data['preset']]
        if data['preset'] == 'custom':
            command += ['--render-scale', str(data['render_scale']),
                                                '--anisotropic', str(data['anisotropic']),
                        '--texture-quality', data['texture_quality'],
                        '--dither', 'on' if data['present_dither'] else 'off']
        if data['fps_target'] == 'unlimited':
            command += ['--present-mode', 'immediate']
        command.append(str(folder))
        return command

    def play(self):
        if self.busy or self.closed:
            return
        target = self.fps_target.get()
        if not self._source_ready():
            messagebox.showwarning('Pasta do jogo', 'Selecione uma pasta que contenha default.xex.')
            self.status.set('Selecione uma pasta válida com default.xex.')
            return
        if not self._engine_ready(target):
            self.generate_native()
            return
        if not self._confirm_target(target):
            self.status.set(f'{graphics.TARGET_LABELS[target]} cancelado • 30 fps continua sendo o padrão')
            return
        if not self.save_settings(quiet=True):
            return
        kind = TARGET_TITLES[target]
        # All Tk variable reads happen here, on the main thread. The worker
        # must only deal with plain values so Tcl is never touched off-thread.
        folder = Path(self.source.get()).expanduser()
        try:
            graphics_data = self._graphics_data()
        except (PortError, tk.TclError) as exc:
            self.status.set(str(exc))
            return
        command = self.play_command(folder)
        def action():
            checked = subprocess.run(command + ['--dry-run'], capture_output=True, text=True,
                                     timeout=30, cwd=PROJECT, env=external_env())
            self.cancel.check()
            if checked.returncode:
                raise PortError('EXPERIMENTAL_VALIDATION', (checked.stderr or checked.stdout).strip()
                                or 'A validação da instalação falhou.')
            output = PROJECT / '.aster/reports' / f'launcher-play-{time.time_ns()}.log'
            output.parent.mkdir(parents=True, exist_ok=True)
            process = None
            try:
                with output.open('w') as console:
                    console.write(checked.stdout)
                    console.flush()
                    with self.experimental_lock:
                        self.cancel.check()
                        if self.closed:
                            raise PortError('CANCELLED', 'Launcher fechado antes de iniciar o jogo.')
                        process = subprocess.Popen(command, cwd=PROJECT, stdout=console,
                                                   stderr=subprocess.STDOUT, env=external_env())
                        self.experimental_process = process
                    self.queue.put(('event', '', {
                        'task': kind, 'state': 'running',
                        'message': f'{graphics.TARGET_LABELS[target]} aberto. '
                                   f'Preset {graphics.PRESET_LABELS[graphics_data["preset"]]}. '
                                   'Feche a janela do jogo ou use Encerrar sessão.',
                        'log': str(output), 'pid': process.pid}))
                    code = process.wait()
                self.cancel.check()
                if code:
                    raise PortError('EXPERIMENTAL_EXIT', f'A sessão terminou com código {code}. Consulte {output}')
                return {'ready': False, 'experimental': target != '30', 'fps_target': target,
                        'graphics_preset': graphics_data['preset'],
                        'graphics': graphics_data, 'exit_code': code, 'log': str(output)}
            finally:
                with self.experimental_lock:
                    if self.experimental_process is process:
                        self.experimental_process = None
        self.start(action, kind)
        self.stop_experimental_button.configure(state='normal')

    def play_experimental(self):
        self.play()

    def play_experimental_60fps(self):
        self.choose_target('60')
        self.play()

    # -------------------------------------------------------------- utilities
    def set_summary(self, text):
        self.summary.configure(state='normal')
        self.summary.delete('1.0', 'end')
        self.summary.insert('end', text)
        self.summary.configure(state='disabled')

    def log(self, event):
        self.events.append(event)
        self.events = self.events[-1000:]
        self.logs.configure(state='normal')
        self.logs.insert('end', json.dumps(event, ensure_ascii=False) + '\n')
        if int(self.logs.index('end-1c').split('.')[0]) > 1500:
            self.logs.delete('1.0', '500.0')
        self.logs.see('end')
        self.logs.configure(state='disabled')
        if event.get('task') and event.get('state'):
            name = event['task']
            values = (event['state'], f"{event['seconds']:.3f}s" if 'seconds' in event else '—')
            if self.task_tree.exists(name):
                self.task_tree.item(name, values=values)
            else:
                self.task_tree.insert('', 'end', iid=name, text=name, values=values)

    def select(self):
        p = filedialog.askopenfilename(title='Selecionar ISO ou XEX',
                                      filetypes=[('Dumps Xbox 360', '*.iso *.ISO *.xex *.XEX'),
                                                 ('Todos', '*')])
        if p:
            self.source.set(p)
            self.save_settings(quiet=True)
            self.inspect()

    def select_folder(self):
        p = filedialog.askdirectory(title='Pasta com default.xex e assets do jogo', mustexist=True)
        if p:
            self.source.set(p)
            self.save_settings(quiet=True)
            self.inspect()

    def select_workspace(self):
        p = filedialog.askdirectory(title='Selecionar diretório de trabalho dentro do projeto',
                                    initialdir=str(PROJECT), mustexist=True)
        if p:
            self.workspace.set(p)

    def open_profile(self):
        path = PROJECT / PROFILE_FILES[self.fps_target.get()] / 'user'
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == 'win32':
                import os
                os.startfile(path)
            else:
                subprocess.Popen(['xdg-open', str(path)], env=external_env())
        except OSError as exc:
            self.status.set(f'Não foi possível abrir o perfil: {exc}')

    def start(self, action, kind):
        if self.busy:
            return False
        self.busy = True
        self.cancel = Cancellation()
        self._set_busy_controls(False)
        self.progress.configure(mode='indeterminate')
        self.progress.start(15)
        self.task_started = time.monotonic()
        self.status.set('Tarefa em andamento…')
        self.log({'task': kind, 'state': 'running'})

        def worker():
            try:
                result = action()
                self.queue.put(('done', kind, result))
            except PortError as exc:
                self.queue.put(('error', kind, exc.as_dict()))
            except Exception as exc:
                self.queue.put(('error', kind, {'code': 'UNEXPECTED', 'message': str(exc)}))

        threading.Thread(target=worker, daemon=True).start()
        return True

    def inspect(self):
        value = self.source.get()
        self.start(lambda: inspect_source(value, self.cancel), 'Inspecionar')

    def prepare(self):
        try:
            cfg = self.config()
            settings.save(cfg, PROJECT)
        except (PortError, OSError) as exc:
            self.status.set(str(exc))
            self.log({'task': 'Preparar', 'error': str(exc)})
            return
        self.start(lambda: prepare(cfg['source'], Workspace(cfg['workspace'], PROJECT), GreenLantern(),
                                   self.cancel, emit=lambda e: self.queue.put(('event', '', e)),
                                   config={'build_type': cfg['build_type'], 'jobs': cfg['jobs']}),
                   'Preparar')

    def generate_native(self):
        if self.busy or self.closed:
            return
        try:
            cfg = self.config()
        except PortError as exc:
            self.status.set(str(exc))
            return
        if not self._source_ready():
            messagebox.showwarning('Dump extraído', 'Selecione a pasta com default.xex e os assets.')
            return
        consent = messagebox.askyesno('Gerar port local',
            'O XEX será verificado e recompilado neste PC. Os arquivos originais não serão alterados.\n\n'
            'Se faltar o SDK ReXGlue 0.10.0, baixar o pacote oficial e conferir seu SHA-256? '
            'Linux: até 172 MB com fontes públicas do cache; Windows: cerca de 43 MB.\n\n'
            'É necessária uma toolchain C++23 instalada. Nenhuma ferramenta será instalada globalmente.')
        if not consent:
            return
        source, jobs = cfg['source'], cfg['jobs']
        self.start(lambda: build_native(source, Workspace(PROJECT / '.aster', PROJECT),
                    self.cancel, emit=lambda e: self.queue.put(('event', '', e)),
                    jobs=jobs, allow_download=True), 'Gerar port')
        self.tabs.select(self.diag_tab)

    def doctor(self):
        self.start(lambda: diagnostics(self.cancel), 'Diagnóstico')

    def clear_cache(self):
        if messagebox.askyesno('Limpar cache', 'Apagar somente cache/v1 dentro do diretório de trabalho?\n'
                               'As origens, os relatórios e as saídas serão preservados.'):
            try:
                Workspace(self.workspace.get(), PROJECT).clear_cache(confirmed=True)
                self.log({'task': 'Limpar cache', 'state': 'completed'})
            except (PortError, OSError) as exc:
                messagebox.showerror('Falha', str(exc))

    def export_report(self):
        try:
            work = Workspace(self.workspace.get(), PROJECT)
            p = work.write_json(f'reports/launcher-{time.time_ns()}.json',
                                {'schema': 2, 'ready': False, 'source': self.source.get(),
                                 'graphics': self._graphics_data(), 'last_result': self.last_result,
                                 'environment': self.last_environment, 'events': self.events})
            self.report_path.set(str(p))
            self.status.set('Diagnóstico salvo localmente')
        except (PortError, OSError) as exc:
            self.status.set(str(exc))

    def copy_logs(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.logs.get('1.0', 'end'))
        self.status.set('Logs copiados para a área de transferência')

    def show_source(self, value):
        info = value.get('source', value)
        title = info.get('title_id')
        identity = ('Title ID corresponde ao módulo Green Lantern; revisão ainda não confirmada.'
                    if title == GreenLantern.title_id else
                    'Title ID de outro jogo.' if title else 'Jogo ainda não identificado por Title ID.')
        lines = [f"Formato: {info.get('format', 'desconhecido')}  |  Title ID: {title or 'não disponível'}",
                 identity, f"Executável/entrada: {info.get('path', '')}"]
        if info.get('format') == 'xex2':
            lines += [f"Acesso ao código: {info.get('code_access', 'não determinado')}",
                      f"Criptografia: {info.get('encryption')} | Compressão: {info.get('compression')}"]
        if info.get('game_directory'):
            lines += [f"Pasta: {info['game_directory']}",
                      f"Inventário: {info['file_count']} arquivos / {info['total_bytes']:,} bytes",
                      f"Outros arquivos (possíveis assets): {info['asset_file_count']}. Completude não verificada.",
                      '', 'Arquivos (amostra):']
            lines += [f"  {r['path']}  ({r['size']:,} bytes)" for r in info['inventory'][:12]]
        else:
            lines += ['XEX isolado não garante assets; selecione a pasta extraída para inventariá-los.']
        if value.get('sha256'):
            lines += ['', f"SHA-256: {value['sha256']}",
                      f"Dependências ausentes: {', '.join(value['missing_dependencies']) or 'nenhuma das sondadas'}",
                      f"Preparação salva. Bloqueio: {value.get('blocker', 'NO_NATIVE_BACKEND')}."]
        if value.get('analysis'):
            analysis = value['analysis']
            lines += ['', 'PE decodificado e validado para este hash de origem.',
                      f"Imports identificados: {analysis['imports']['unique_apis']} APIs."]
            if analysis.get('native_leaf_probe'):
                lines += ['Experimento nativo de uma função: 10.000 casos aprovados. Não é execução do jogo.']
            lines += ['Runtime e backend integral do jogo ainda pendentes.']
        self.set_summary('\n'.join(lines))
        self.source_status.set(f"Jogo / {'Title ID reconhecido' if title == GreenLantern.title_id else 'identidade não confirmada'}")
        self.tabs.select(self.game_tab)

    def poll(self):
        while True:
            try:
                state, kind, value = self.queue.get_nowait()
            except queue.Empty:
                break
            if state == 'event':
                self.log(value)
                self.status.set(value.get('message') or f"{value.get('task')} • {value.get('state')}")
                continue
            self.busy = False
            self.progress.stop()
            self.progress.configure(mode='determinate', value=0)
            self._set_busy_controls(True)
            self._refresh_engine_status()
            self.last_result = value
            self.log({'task': kind,
                      'state': ('cancelled' if value.get('code') == 'CANCELLED' else 'failed')
                      if state == 'error' else 'blocked' if value.get('state') == 'blocked' else 'completed',
                      'seconds': time.monotonic() - self.task_started,
                      **({'error': value} if state == 'error' else {})})
            if state == 'error':
                self.status.set(f"{value['code']} • {value['message']}")
                self.set_summary(json.dumps(value, indent=2, ensure_ascii=False))
                if kind == 'Inspecionar':
                    self.source_status.set('Jogo / entrada inválida ou não suportada')
            elif kind == 'Diagnóstico':
                self.last_environment = value
                missing = [n for n in GreenLantern().dependencies()
                           if not value['tools'].get(n, {}).get('available')]
                self.environment_status.set(
                    f"Ambiente / {'faltam: ' + ', '.join(missing) if missing else 'ferramentas básicas disponíveis'}")
                self.environment.configure(state='normal')
                self.environment.delete('1.0', 'end')
                self.environment.insert('end', '\n'.join(
                    f"{name}: {tool.get('version') or ('não encontrado' if not tool['available'] else 'versão não confirmada')}"
                    for name, tool in value['tools'].items()))
                ghidra = value.get('ghidra', {})
                self.environment.insert('end', f"\nGhidra local: {ghidra.get('version') or 'não encontrado'}\n"
                                               'REA MCP: acesso não consultado pelo launcher independente')
                self.environment.configure(state='disabled')
                self.status.set('Diagnóstico concluído • port nativo em validação')
            elif kind == 'Gerar port':
                self.status.set('Port gerado localmente • pronto para testar a inicialização')
                self.set_summary(value.get('message', '') + '\n' + str(value.get('binary', '')))
                self._refresh_engine_status()
                self.tabs.select(self.play_tab)
            elif kind.startswith('Jogar'):
                target = value.get('fps_target', self.fps_target.get())
                if target == '60':
                    self.status.set('Sessão 60 fps encerrada • timestep medido; validação humana pendente')
                elif target == 'unlimited':
                    self.status.set('Sessão ilimitada encerrada • modo experimental; valide a sensação no jogo')
                else:
                    self.status.set('Sessão 30 fps encerrada • campanha completa ainda não validada')
                self.report_path.set(value['log'])
            else:
                self.show_source(value)
                self.status.set('Inspeção concluída • port nativo em validação' if kind == 'Inspecionar'
                                else f"Relatório salvo • compilação bloqueada: {value.get('blocker', 'NO_NATIVE_BACKEND')}")
                if kind == 'Preparar':
                    self.tabs.select(self.game_tab)
        self._refresh_play_state()
        self.after_id = self.root.after(50, self.poll)


def main():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise PortError('DISPLAY_UNAVAILABLE', 'Não foi possível abrir o display gráfico.',
                        reason=str(exc)) from exc
    Launcher(root)
    root.mainloop()
