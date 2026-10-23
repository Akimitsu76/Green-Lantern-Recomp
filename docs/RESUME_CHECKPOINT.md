# Ponto de retomada — 22–23/10/2026

## Atualização — gerador portátil (23/10/2026)

O estado atual está em [PORTABLE_BUILD.md](PORTABLE_BUILD.md). O fluxo real
baixa SDK fixado com hash, gera C++ local, compila e registra artefatos por hash.
Build repetido íntegro não executa codegen nem compilador. O Linux reproduz o
plugin com cache persistente; o Windows usa D3D12/ROV ainda sem validação nativa.
As quatro falhas da revisão foram corrigidas: relógio guest com VSync off,
MSAA sem efeito, Cancelar invertido e destinos não registrados ignorados.

Os resultados abaixo são históricos. Não certificam o novo host em toda a
campanha. As medições atuais e os hashes dos pacotes ficam no relatório local
`.aster/reports/portable-release-validation.json`.


## Estado atual — launcher, presets e alvos

- Launcher redesenhado em abas **Jogar**, **Gráficos**, **Jogo e arquivos** e
  **Diagnóstico**, com tema escuro, cards, status de build e validação antes de
  abrir. Tamanho padrão 1160×720; mínimo 1088×696.
- Presets gráficos **Baixa**, **Padrão**, **Alta**, **Ultra** e
  **Personalizada** na aba **Gráficos**. Eles traduzem valores para CVars reais
  de resolução interna, MSAA, anisotrópico, cache de texturas e dithering.
- Alvos **30 fps** (padrão), **60 fps** (build v9, perfil isolado) e
  **Ilimitado** (build v10, perfil isolado, VSync off, apresentação imediata).
  60 e ilimitado são opt-in, pedem confirmação e não alteram o save de 30 fps.
- Preferências do launcher em `.aster/config/settings.json`, schema 2; schema 1
  é migrado em memória e salvo como 2. Nenhum preset/alvo escreve no perfil ou
  nos saves do jogo.
- Build v10: `.aster/build/rex-fps-unlimited-v10/aster_green_lantern`, SHA-256
  `2e9069aa99ac8bce65f70c01149ec696d253922b92a4cba2cb29b09bcb9955f1`.
  Plugin `2760fb7b285370737f78569e261b6ddc5e46afb0040a5fc44d29b50af15d4249`.
- Probe ilimitado final `unlimited-gameplay-003`: 90,16 s, 38.627 apresentações
  (428,4/s), FSI, entradas de teclado enviadas, sem fatal. `ASTER_SIM` manteve
  alvo 60 e simulação em tempo real; GPU global 95–96% / ~91–107 W nas amostras
  finais. `gameplay_verified=false` e sem captura X11 de gameplay.
- Probe curto do build principal de 30 fps com preset Padrão
  (`preset30-default-001`, 12,52 s): XEX carregado, CVars aceitas, 461
  apresentações, FSI/FIFO, perfil isolado e nenhum fatal. `ready=false` pelo
  prazo curto; confirma aceitação das flags, não gameplay.
- Referências: 30 fps `.aster/reports/rexglue-runtime-probe.json` (047); 60 fps
  `.aster/reports/rexglue-runtime-probe-60fps.json` (057); ilimitado
  `.aster/reports/rexglue-runtime-probe-unlimited.json` (003).
- `play_green_lantern.py --validar` passou nos três alvos. Suíte completa:
  **152 testes aprovados**, sem falhas/skips, em Xvfb 1440×900.
- Config real restaurada para **30 fps + preset Padrão**, preservando o caminho
  do dump. O build duplicado `rex-rex-fps-unlimited-v10` foi auditado e
  removido; as arenas SHM não foram limpas nesta rodada.
- Pendente do usuário: avaliar visualmente Baixa/Alta/Ultra, confirmar a sensação
  de 60/ilimitado, áudio, campanha e outras GPUs. Não executar testes que exijam
  controle humano até o retorno.

## Investigação atual: cadência da engine

- Binário e plugin principais permanecem preservados; referência estável047.
- 048/049/051 isolam a espera fora da apresentação/renderização; 052 confirma
  `82402E38` esperando cerca de33ms com alvo30 em `82836A24`. Seletor original
  `82375A28` suporta30/60 (25/50 em outro modo). Veja FPS_PROGRESS.md.
- Builder `scripts/build_rex_experiment.py` relinka114 objetos em pasta separada,
  sem codegen ou staging. Hook fica em integrations/rexglue/experiments/.
- 050/v4 falhou por leitura diagnóstica da pilha não mapeada. Reassessment registra
  a falha; leitura removida em v5. Parser agora detecta access violations.
- 054/v7 alcançou checkpointLv.2, deslocamento e ataque visual;59,87 chamadas de
  frame/s após105s, retorno0 em190,86s, semfatal/XEXintacto. Seletor60 opt-in
  desligado por padrão; o v7 não foi integrado ao launcher. 053 ficou no título.
- 055/v9 rodou o baseline de30fps no mesmo build experimental, com perfil
  idêntico ao de60: mediana de30,000 chamadas de render/s, delta1,02038s/s,
  passo de simulação0,99993 e150 subpassos por janela de5s. Terminou em208,9s
  quando a janela fechou, retorno0, sem fatal/XEXintacto.
- 056/v9 rodou o alvo60 com o mesmo build e perfil: mediana de59,997 chamadas
  de render/s, delta1,02032s/s, passo de simulação0,99996 e300 subpassos por
  janela de5s. Alcançou o checkpointLv.2, retorno0 em240,22s por prazo, sem
  fatal/XEXintacto. O delta de~2% é comum aos dois alvos; o alvo60 não o criou.
- 057 validou o caminho do launcher 60fps: buildv9, FSI, perfil isolado
  `green-lantern-60fps`, 45,18s, sem fatal, XEXintacto; referência estável em
  `.aster/reports/rexglue-runtime-probe-60fps.json`. O launcher ganhou o alvo
  opt-in de 60 fps na aba **Gráficos**, com confirmação e perfil próprio;
  30 fps continua o padrão.
- 058/sessão humana 60fps: 412,04s, retorno0, sem fatal, XEXintacto, perfil
  humano igual ao backup. 81 janelas de simulação, todas com alvo60; mediana de
  300 chamadas/subpassos, delta0,999949. Apresentação mediana59,995/s, com6
  janelas abaixo de59 e3 abaixo de55. Capturas mostram combate, pausa, cutscene
  e carregamento. A percepção de golpes/física/animações/áudio e dos engasgos
  ainda precisa do relato humano; não é certificação automática.
- GPU global na janela60–200s:30fps~31,67%/39,33W;60fps~57,41%/56,98W. Na
  sessão humana058, mediana global de67,5%/58,72W, sem pareamento de cena. É
  telemetria da placa inteira, não benchmark determinístico.
- Evidência `.aster/reports/fps-validation-results.json` e
  `.aster/reports/rex-history/055-validation-30fps/`, `056-validation-60fps/`,
  `057-60fps-launcher-validation/` e `058-human-60fps/`. Fonte do hookv9 em
  `.aster/build/rex-fps-validation-v9/hook.cpp`. Referência principal047
  restaurada, launcher `--validar` passou. Todos os probes encerrados;
  acompanhamento027 pausado.
- Na rodada 055/056, 129 testes passaram em 2,148 s, zero falhas/skips. Saves
  humanos iguais ao backup.

## Estado atual: apresentação e GPU

- Launcher com VSync on agora pede apresentação FIFO; rollback somente dessa
  escolha: `python3 scripts/play_green_lantern.py --vsync on --present-mode auto`.
- GPU local observada: imediato ~83–84%/70 W; FIFO ~35–41%/43–48 W em checkpoint
  e combate, mantendo recursos gráficos e vblank. Não é benchmark determinístico
  nem garantia para toda a campanha. Na rodada de apresentação, 121 testes
  passaram (1,950 s), zero skips.
- Referência atual:047-gpu-controlled-synchronized. Plugin principal permanece
  2760fb7b285370737f78569e261b6ddc5e46afb0040a5fc44d29b50af15d4249; CPU intacta.
  Plugin de timestamps ccd67dfc fica isolado em rex-green-gpu-test, sem staging.
- 045/046 partem de perfis idênticos, mas046 ficou no título. Par inválido para
  comparar gameplay. 047 usa sequência adiada e alcança checkpoint; capturas de
  045 mostram combate. Não transformar isso em comparação de frames idênticos.
- 036–039 tiveram SIGBUS na arena de memória, inclusive com plugin antigo.
  Limpeza autorizada de 41 temporários órfãos liberou13.337.702.400 bytes;040
  rodou com o mesmo plugin de036. Runtime ainda usa `_Exit` e deixa arenas SHM:
  vazamento documentado, não corrigido; jamais limpar `/dev/shm` genericamente.
- Nenhum processo do jogo permanece ativo. Saves humanos iguais ao backup027.
  Acompanhamento027 continua pausado. FPS livre e sombras continuam pendentes.
- Veja GPU_OPTIMIZATION.md e .aster/reports/gpu-presentation-results.json.

## Histórico: atualização do cache

- Sessão humana 027 encerrada com autorização, retorno0, 2152,17s e XEX intacto;
  heartbeat acompanhar-sess-o-green-lantern está PAUSED. Nenhum jogo está aberto.
- Campanha avançou com personagem Lv.2; CONTINUE em cópia do perfil retomou o
  checkpoint em031. Não significa missão2 nem campanha inteira validada.
- Cache Vulkan do driver implementado no pluginRD, snapshot após prewarm e a
  cada10s quando houver pipelinesnovas. Testes030/031 gravaram/carregaram22.743.770
  bytes; 033 rejeitou corrupção e regravou semfatal. Fonte/patch preservados.
- Plugin principal .aster/build/rex-green/librexgpu-xenosrd.so atualizado, SHA256
  2760fb7b285370737f78569e261b6ddc5e46afb0040a5fc44d29b50af15d4249.
  CPUbinário continua com o hash abaixo. Runtime/Tracy correspondem ao SDK RD.
- Rollback: .aster/backups/graphics-before-driver-cache/; saves humanos em
  .aster/backups/user-after-human-027/. Testes usam runtime e perfil separados.
- Opções: --shader-mode async|blocking e --vsync on|off. Defaults async/on.
  GUIConfiguração e ambiente contém os controles. --validar passou após staging.
- 119 testes passaram, zero skips/falhas. As tentativas028/029 são diagnósticos:
  028 carregou RDantigo (reassessment),029 mostrou que shutdown-only não persistia.
- GPU alta permanece: VSync off elevou GPU a97–98%/109W e ficou na tela inicial;
  não é desbloqueio de FPS validado em gameplay. Sombras: ocorrênciaúnica ainda
  não reproduzida. Não afirmar otimizaçãoGPU/sombras/FPS concluída.
- Referência do launcher:031-driver-cache-warm-gameplay (identidades CPU/GPU).
  Último teste técnico:033-driver-cache-corruption. Não retomar heartbeat027.

Veja [GRAPHICS_POLISH.md](GRAPHICS_POLISH.md). Os trechos abaixo são históricos.

O usuário retomou o trabalho e pediu revisão das alterações do OpenCode.
A pausa anterior foi encerrada. Nenhum build ou probe permanece em execução
ao concluir esta revisão.

## Atualização após polimentos e teste de jogabilidade

O ponto mais avançado observado é o grupo após destruir os primeiros destroços,
com o tutorial de defesa. Não foi concluída a missão inteira e não há bloqueio
técnico confirmado nesse ponto. Veja [PLAYABILITY.md](PLAYABILITY.md).

- Última tentativa: `026-jump-and-audio`, 645,77 s, encerrada pelo operador,
  retorno 0 e nenhum fatal/destino não registrado nos logs retidos.
- Tentativa 024: 900,44 s sem fatal; inclui períodos parado, não um benchmark.
- GAME OVER e CONTINUE foram exercitados; a continuação voltou à arena inicial.
- Áudio: stream PipeWire do PID do jogo com sinal não nulo em cerca de seis
  segundos; qualidade/sincronia e campanha completa permanecem pendentes.
- Launcher Tk agora tem as abas **Jogar**, **Gráficos**, **Jogo e arquivos** e
  **Diagnóstico**, com presets, alvos 30/60/ilimitado e validação em worker. A
  CLI tem `--validar`, controles completos e bloqueio de sessões concorrentes,
  também compartilhado pelos novos probes.
- Suíte completa atual: **152 testes aprovados, sem falhas ou skips**.
- Build nativo, SDK e 1.884 hints permaneceram iguais nesta rodada. O hash do
  XEX original continua intacto. Nenhum probe permanece em execução.

## Base técnica preservada

CPU recompilada estaticamente em host Linux x86_64 com ReXGlue v0.10.0 e backend
Xenos/Vulkan do SDK; FSI testado na RTX 5060. Fontes e binários derivados do jogo
continuam privados. Os 1.884 hints incluem a recuperação de `0x8220D2D0` como
tail branch de quatro bytes; 21 limites automáticos continuam em quarentena.
Não usar `--force` ou retornos artificiais para esconder destinos desconhecidos.

O relatório `.aster/reports/rexglue-runtime-probe.json` aponta à tentativa 047;
o modo 60 fps usa `.aster/reports/rexglue-runtime-probe-60fps.json` (057); o
ilimitado usa `.aster/reports/rexglue-runtime-probe-unlimited.json`
(`unlimited-gameplay-003`). `ready=false` e `gameplay_verified=false` permanecem
intencionais. A suíte atual:

```sh
xvfb-run -a -s '-screen 0 1440x900x24' python3 -m unittest discover -s tests -v
```

A revisão anterior está em [OPENCODE_REVIEW.md](OPENCODE_REVIEW.md). O projeto
não tinha commit base; não atribuir todas as linhas a um agente por suposição.

## Abrir a compilação experimental

```sh
python3 scripts/play_green_lantern.py --validar
python3 scripts/play_green_lantern.py
```

Para o alvo 60 opt-in:

```sh
python3 scripts/play_green_lantern.py --fps-target 60 --validar
python3 scripts/play_green_lantern.py --fps-target 60
```

Para o alvo ilimitado opt-in:

```sh
python3 scripts/play_green_lantern.py --fps-target unlimited --validar
python3 scripts/play_green_lantern.py --fps-target unlimited
```

Ou abrir o launcher Tk, selecionar a pasta do dump, escolher o preset/alvo na aba
**Gráficos** e usar **Jogar agora**. Consulte
[EXPERIMENTAL_PLAY.md](EXPERIMENTAL_PLAY.md) e
[GRAPHICS_PRESETS.md](GRAPHICS_PRESETS.md) para os controles completos.
Saves, cache e configurações de 30 fps ficam em
`.aster/runtime/green-lantern/`; 60 fps usa
`.aster/runtime/green-lantern-60fps/`; ilimitado usa
`.aster/runtime/green-lantern-unlimited/`. Nenhum deles altera o save de 30 fps.

## Identidade e caminhos

- Jogo: `/mnt/disco/games/Jogos/xbox 360/Green_Lantern`.
- SHA-256 do `default.xex`:
  `3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1`.
- Executável principal: `.aster/build/rex-green/aster_green_lantern`.
- SHA-256 do executável principal testado:
  `7c7b81dd74f27623c1976bb0a3a3ed916575da060076cc77bf581b0632bda970`.
- Build 60 fps: `.aster/build/rex-fps-validation-v9/aster_green_lantern`,
  SHA-256 `906d300dea1284ead441efbe5853017c71f3775ee1e61864668ef46923a8cfdd`.
- Build ilimitado: `.aster/build/rex-fps-unlimited-v10/aster_green_lantern`,
  SHA-256 `2e9069aa99ac8bce65f70c01149ec696d253922b92a4cba2cb29b09bcb9955f1`.
- Plugin gráfico:
  `2760fb7b285370737f78569e261b6ddc5e46afb0040a5fc44d29b50af15d4249`.
- Saves: `.aster/runtime/green-lantern/user`.
- Referências FSI: `rexglue-runtime-probe.json` (30),
  `rexglue-runtime-probe-60fps.json` (60) e
  `rexglue-runtime-probe-unlimited.json` (ilimitado).
- Histórico de execução: `.aster/reports/rex-history/`.
- Análises, imagens PE e hints em quarentena: `.aster/analysis/green-lantern/`.

## Próxima validação

Concluir manualmente o tutorial de defesa, ativar o primeiro salto contextual,
atingir um checkpoint posterior e conferir CONTINUE em uma nova sessão. Validar
qualidade/sincronia de áudio, combate prolongado, desempenho e outras GPUs.
Comparar visualmente Baixa/Padrão/Alta/Ultra no mesmo trecho e registrar a
sensação de 60/ilimitado (tearing, engasgos, física, animações e áudio). Para o
alvo 60, comparar duração de golpes e comportamento no mesmo trecho antes de
considerar integração; o passo de simulação já foi medido, mas isso não certifica
o comportamento visual ou de combate. Para o ilimitado, confirmar visualmente o
gameplay e a estabilidade; a evidência atual é automatizada e tem
`gameplay_verified=false`.

Os probes agora aceitam `--live-input`; comandos de `scripts/rex_probe_input.py`
são pedidos enfileirados, cuja execução e captura devem ser conferidas em
`live-results.jsonl`. O encerramento com `--stop` preserva o relatório e verifica
o XEX. Consulte a integração ReXGlue para reprodução. Nenhum processo foi deixado
aberto ao finalizar esta rodada.
