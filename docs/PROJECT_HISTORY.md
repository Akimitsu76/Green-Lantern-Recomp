# Aster Native

Framework experimental de portabilidade e launcher desktop original, com módulo
inicial para **Green Lantern: Rise of the Manhunters (Xbox 360)**.

**Port experimental, ainda sem validação completa de jogabilidade.** O host
Linux com ReXGlue/Vulkan alcança título, menus, abertura e a primeira fase com
HUD, cenário/personagens visíveis, combate inicial e passagem dos primeiros
destroços até o tutorial de defesa. Há sinal de áudio medido no stream do jogo. O modo
Vulkan FSI corrigiu a geometria preta nas cenas testadas; o padrão FBO falhou. A revisão
das mudanças do OpenCode corrigiu o analisador e isolou 21 limites de função
não comprovados. Veja [a revisão](docs/OPENCODE_REVIEW.md) e o
[estado de jogabilidade](docs/PLAYABILITY.md).

## Launcher portátil e geração local — 23/10/2026

O launcher agora gera e compila o host a partir da pasta extraída do jogo,
verifica a revisão do XEX e reutiliza builds íntegros. Os pacotes Windows ZIP
(com `.exe`) e Linux TAR.GZ ficam em `dist/`. Incluem Python/Tk e CMake/Ninja;
a toolchain C++23 continua necessária. Não incluem jogo nem código recompilado.
Veja [instalação e requisitos](docs/PORTABLE_BUILD.md).

Corrigidos: VSync off acelerando o relógio guest nos alvos 30/60, falso controle
de MSAA, botão Cancelar invertido e validação ignorando destinos não registrados.
A geração e inicialização Linux foram testadas; o launcher Windows abriu no
Wine. A compilação e o jogo Windows ainda exigem validação em Windows real.

## Atualização gráfica

Cache persistente do driver Vulkan integrado e testado em duas aberturas, com
recuperação de arquivo corrompido. Novos shaders compilam em segundo plano por
padrão; os conhecidos são preparados na entrada. A apresentação sincronizada FIFO
reduziu o uso observado da GPU de cerca de 83–84%/70 W para 35–41%/43–48 W em
trechos locais, mantendo a configuração gráfica. Já é o padrão com VSync ligado.
Outros trechos/GPUs, a avaliação humana subjetiva dos presets e a ocorrência
isolada de sombra continuam pendentes. A sessão humana 058 confirmou gameplay
real em 60 fps, combate, pausa, cutscene e carregamento; falta registrar a
percepção de física, animações, áudio e engasgos. Veja
[GPU_OPTIMIZATION.md](docs/GPU_OPTIMIZATION.md) e
[GRAPHICS_POLISH.md](docs/GRAPHICS_POLISH.md).

O launcher foi redesenhado com as abas **Jogar**, **Gráficos**, **Jogo e
arquivos** e **Diagnóstico**. A aba **Gráficos** oferece os presets **Baixa**,
**Padrão**, **Alta**, **Ultra** e **Personalizada**, além dos alvos **30 fps**,
**60 fps** e **Ilimitado**. **30 fps continua o padrão.** 60 fps usa o build v9 e
um perfil isolado; o modo ilimitado usa o build v10, desliga VSync e usa
apresentação imediata. Esses dois alvos são opt-in, pedem confirmação e não
alteram o save de 30 fps. As preferências do launcher ficam apenas em
`.aster/config/settings.json` (schema 2); nenhum preset grava no perfil do jogo.
Veja o [guia de presets](docs/GRAPHICS_PRESETS.md).

O alvo 60 opt-in foi medido em par com o alvo 30: o passo de simulação acompanha
o tempo de parede nos dois e o delta de ~2% é comum aos dois alvos. O alvo 60
alcançou o checkpoint Lv.2 sem fatal. Na sessão humana 058, as capturas mostram
combate, menu de pausa, cutscene e carregamento; a mediana foi 59,995
apresentações/s, com seis janelas de 5 s abaixo de 59. O modo ainda não é FPS
livre nem certificação de física, animações ou áudio.

O modo ilimitado v10 foi exercitado por 90,16 s em FSI, com 38.627
apresentações (média de 428/s), alvo de simulação 60 em tempo real, entradas de
teclado enviadas e sem erro fatal. O probe ainda registra
`gameplay_verified=false`; não há captura visual de gameplay no Xwayland nesta
máquina. Veja [FPS_PROGRESS.md](docs/FPS_PROGRESS.md).

**A suíte atual tem 152 testes aprovados, sem falhas ou skips**, executada com
Xvfb em 1440×900.

## Estado em 23/10/2026

- Núcleo Python sem dependências pip: inspeção estrutural XEX2/XDVDFS, SHA-256,
  relatórios, diretórios limitados ao projeto, API de módulo v1 e cancelamento.
- Launcher Tk: seleção de pasta extraída, ISO ou XEX, inventário de assets,
  diagnóstico, tarefas reais, logs exportáveis e cancelamento. Preferências de
  diretório de trabalho, presets e alvo persistentes; limpeza confirmada do
  cache. Compilar/iniciar completos continuam desabilitados. **Jogar agora** abre
  o build local após validar dump, build, plugin e referência FSI. O alvo e o
  preset ficam na aba **Gráficos**; 30 fps é o padrão, e 60/ilimitado são opt-in
  com confirmação e perfis isolados.
- Utilitário C++ próprio compilado e executado para verificar o compilador local.
- ISO inicial sem assinatura XDVDFS. Nova pasta extraída fornecida pelo usuário:
  XEX identificado como Green Lantern, 135 arquivos / 3,60 GB. O XEX declara
  criptografia e compressão basic; decodificação local concluída após autorização.
- XenonRecomp compilado localmente; Ghidra identificou 12.534 funções, com
  limitações documentadas. Imports resolvidos: 451 registros / 232 APIs distintas.
- ReXGlue v0.10.0: análise passou com hints próprios, sem `--force`; executável
  Linux compilado. Menus respondem ao teclado; perfil local foi criado e lido
  novamente. Combate, destruição de obstáculos, tutorial de defesa e retomada após derrota
  foram observados com FSI. Há saída de áudio não nula atribuída ao jogo; qualidade
  e sincronia, campanha completa e outras GPUs continuam sem validação.

## Uso direto, sem instalação

Na raiz deste projeto:

```sh
python3 -m native_port doctor
python3 -m native_port gui
python3 -m native_port inspect '/caminho/jogo.iso'
python3 -m native_port prepare '/caminho/pasta-do-jogo'
python3 scripts/survey_image.py '/caminho/jogo.iso'
python3 scripts/host_probe.py
python3 -m unittest discover -s tests -v
xvfb-run -a -s '-screen 0 1440x900x24' python3 -m unittest discover -s tests -v
```

Também pode executar `./apps/launcher/aster-native` a partir da raiz.

Para abrir a **compilação experimental local já testada**, com teclado e Vulkan FSI:

```sh
python3 scripts/play_green_lantern.py
```

O comando usa a pasta do último probe e verifica os hashes do XEX, do executável e
do plugin. Também aceita a pasta como argumento. Enter = Start, Espaço = A,
Backspace = B, WASD = stick esquerdo, L = X. Feche a janela para encerrar.
Logs/cache/saves ficam em `.aster/`. Presets e alvos também podem ser escolhidos
na linha de comando:

```sh
python3 scripts/play_green_lantern.py --graphics-preset high --validar
python3 scripts/play_green_lantern.py --graphics-preset high

python3 scripts/play_green_lantern.py --fps-target 60 --validar
python3 scripts/play_green_lantern.py --fps-target 60

python3 scripts/play_green_lantern.py --fps-target unlimited --validar
python3 scripts/play_green_lantern.py --fps-target unlimited
```

O alvo 60 usa o build v9 e o perfil isolado
`.aster/runtime/green-lantern-60fps/`. O alvo ilimitado usa o build v10 e o perfil
`.aster/runtime/green-lantern-unlimited/`, com VSync desligado e apresentação
imediata. Nenhum deles altera o save de 30 fps. `--experimental-60fps` continua
aceito como atalho antigo. O modo FSI exige suporte a fragment shader interlock;
foi testado na RTX 5060 local. Isso não habilita o backend completo no launcher
Tk.

No launcher, clique em **Selecionar pasta do jogo…** e indique a pasta com
`default.xex` e os demais arquivos extraídos. Não mova somente o XEX para uma
pasta vazia: o jogo dependerá também dos seus assets. O botão **Jogar agora** só
habilita quando o build e a referência do alvo escolhido estão presentes; a aba
**Jogo e arquivos** mostra o que falta.

Python >=3.11; Tkinter/Tk para GUI; compilador C++17 para o utilitário opcional.
Use um terminal da sessão gráfica para abrir o launcher. Os testes da GUI usam
Xvfb; para capturar a janela inteira, use uma tela de pelo menos 1440×900.

`inspect` retorna 0 para estrutura reconhecida e 2 para erro. `prepare` retorna 3
quando salva preparação mas para no backend ausente; isso não significa jogo pronto.
Os resultados ficam em `.aster/`, ignorado pelo Git. `survey_image` lê a imagem
inteira para calcular hash e localizar assinaturas; pode levar tempo e aceita Ctrl+C.
Não faz descriptografia nem extração.

O CMakeLists da raiz cria somente `aster-host-probe` e foi configurado/compilado.
CMake 3.31.10 fica em `.aster/tools/cmake-runtime`; não altera o PATH global.
A integração de análise fica em `integrations/xenonrecomp`. Veja NATIVE_PROGRESS
e BUILD_PIPELINE para reproduzir o experimento.

## Documentação

- [Progresso nativo e evidências atuais](docs/NATIVE_PROGRESS.md)
- [Estudo dos ports indicados pelo usuário](docs/PORT_REFERENCES.md)
- [Licenças das ferramentas](docs/TOOLING_LICENSES.md)
- [Ambiente inicial](docs/ENVIRONMENT.md)
- [Viabilidade e fontes técnicas](docs/FEASIBILITY.md)
- [XEX real e avaliação do XenonRecomp](docs/XENONRECOMP_EVALUATION.md)
- [Arquitetura](docs/ARCHITECTURE.md)
- [Engenharia reversa](docs/REVERSE_ENGINEERING.md)
- [Pipeline](docs/BUILD_PIPELINE.md)
- [Módulos](docs/GAME_MODULES.md)
- [Desenvolvimento e testes](docs/DEVELOPMENT.md)
- [Resultados da validação](docs/VALIDATION.md)
- [Presets gráficos e alvo de FPS](docs/GRAPHICS_PRESETS.md)
- [Abrir a compilação experimental](docs/EXPERIMENTAL_PLAY.md)
- [Limitações](docs/KNOWN_LIMITATIONS.md)

Não adicione dumps, assets, código gerado proprietário ou chaves ao repositório.
Ferramentas de terceiros ficam isoladas em `.aster/tools`, com suas licenças.

Investigação atual de cadência e experimentos isolados: [FPS_PROGRESS.md](docs/FPS_PROGRESS.md).
