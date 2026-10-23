# Experimento ReXGlue local

Requer o SDK v0.10.0 já extraído em `.aster/tools/rexglue-0.10.0/linux-amd64`,
CMake local, Clang/Ninja e o XEX do usuário com o hash documentado em
`games/green_lantern_rex_hints.toml`. Não baixa nem instala ferramentas.

O projeto inicial foi criado com `rexglue init`:

```sh
.aster/tools/rexglue-0.10.0/linux-amd64/bin/rexglue init \
  --project-name aster_green_lantern \
  --xex-path "$PWD/.aster/analysis/green-lantern/source.xex" \
  --game-root "$PWD/.aster/analysis/green-lantern" \
  --project-root "$PWD/.aster/rex/green-lantern"
```

Não repetir `init` sobre um projeto existente sem revisar suas alterações locais.
No manifesto gerado, definir o `includes` da seção `[entrypoint]` como
`["../../../games/green_lantern_rex_hints.toml"]`.
No CMake gerado, solicitar `GPU_PLUGINS xenos` em `rexglue_setup_target`, e acrescentar:

```cmake
include("${CMAKE_CURRENT_SOURCE_DIR}/../../../integrations/rexglue/stage_linux_runtime.cmake")
aster_stage_rex_linux_runtime(aster_green_lantern)
```

O host usa o boilerplate oficial gerado pelo SDK. A execução recebe os caminhos
por flags; não inclui paths absolutos do jogo no código gerado da aplicação.

```sh
.aster/tools/rexglue-0.10.0/linux-amd64/bin/rexglue \
  --log-file .aster/reports/rexglue-codegen-hints.log codegen \
  .aster/rex/green-lantern/aster_green_lantern_manifest.toml
.aster/tools/cmake-runtime/cmake/data/bin/cmake \
  -S .aster/rex/green-lantern -B .aster/build/rex-green -G Ninja \
  -DCMAKE_PREFIX_PATH="$PWD/.aster/tools/rexglue-0.10.0/linux-amd64" \
  -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF \
  -DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF
.aster/tools/cmake-runtime/cmake/data/bin/cmake --build .aster/build/rex-green --parallel 2
python3 scripts/probe_rex_runtime.py '/caminho/Green_Lantern'
```

O probe verifica o hash do XEX, dependências compartilhadas e preservação do XEX
original; limita a execução a 30 s (configurável de 1 a 900), desabilita core dumps
e grava logs/cache/saves localmente. Precisa de sessão gráfica e driver Vulkan.
Retorno 0 do processo não certificaria jogabilidade: o relatório sempre começa
com `ready=false`. Os testes atuais já alcançam a primeira fase; veja OPENCODE_REVIEW.

O probe usa Vulkan FSI obrigatoriamente (a opção antiga de FBO foi removida).
Para entrada e captura, acrescente `--keyboard --capture-window`. Teclas podem ser
enviadas com `--press 27:Return` ou `--press 75:w:2` (segurar W por dois segundos).
São testes de saída/entrada; um evento enviado não certifica gameplay completo.

Para abrir a compilação testada interativamente, na raiz do projeto:

```sh
python3 scripts/play_green_lantern.py
```

Esse frontend verifica a identidade do executável contra o último probe com FSI,
usa os dados do usuário dentro de `.aster/` e mantém o jogo original em modo
somente leitura. Não recompila nem baixa dependências. O modo `--dry-run` valida
o comando sem abrir janela. Campanha completa e qualidade/sincronia de áudio
permanecem pendentes; há sinal de áudio medido no stream do jogo.

Não há CI de gamecode ou distribuição de fontes geradas. Todos os resultados
privados e executáveis ficam em `.aster/`, ignorado pelo Git.

Para testes guiados, habilite `--live-input` no probe. Em outro terminal:

```sh
python3 scripts/rex_probe_input.py LABEL --key w --hold 1
python3 scripts/rex_probe_input.py LABEL --key w+space --hold 1
python3 scripts/rex_probe_input.py LABEL
python3 scripts/rex_probe_input.py LABEL --stop
```

Sem tecla, o pedido solicita uma captura. O helper somente enfileira: confira
`live-results.jsonl` para saber se foi executado. O processo do probe verifica o
PID da sua janela antes de enviar eventos. `--audio-check-at 60` mede somente
streams atribuídos ao processo; deixe pelo menos 35 s antes do limite do probe.
Os novos probes e o launcher compartilham o bloqueio local `play.lock`.
