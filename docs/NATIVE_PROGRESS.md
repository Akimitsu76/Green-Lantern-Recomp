# Experimentos nativos — 22/10/2026

Atualização de polimentos: [PLAYABILITY.md](PLAYABILITY.md) registra o confronto
após os primeiros destroços, áudio com sinal medido e retomada após derrota.
A missão inteira ainda não foi concluída; 115 testes passaram.

## Histórico após revisão do OpenCode

O host alcançou título, menus, criação/leitura de perfil, abertura e a primeira
fase com HUD. O teste 017 durou 150 s sem fatal registrado, mas teve geometria
preta com o backend padrão. O modo FSI corrigiu essa falha nas cenas testadas:
o teste 020 durou 140 s, com cenário/personagens visíveis; o teste 021 durou
115 s e permitiu observar movimento pelo teclado. Ambos terminaram pelo limite
programado, sem fatal registrado. Ainda não há
validação completa de gameplay/áudio/saves. O texto abaixo preserva os experimentos
anteriores. Consulte [OPENCODE_REVIEW.md](OPENCODE_REVIEW.md) para as correções
do analisador e `.aster/reports/rexglue-progress.json` para a evidência local.

O hint adicional de `0x8220D2D0` corrigiu o abort observado no teste 016. A imagem
do cenário/HUD foi conferida em `017-opening-transition/window-27.png`.

## Resultado

O XEX real foi decodificado localmente com o carregador do XenonRecomp, após
a autorização explícita do usuário. **Uma função de oito bytes do jogo foi
recompilada para C++, compilada para x86_64 e executada em 10.000 casos de teste.**
Isso valida somente esse acessor. Separadamente, o experimento ReXGlue abaixo
compilou um host com o código gerado e alcançou o início da thread principal;
o processo abortou em função não registrada. **Ainda não há jogo jogável validado.**

O SHA-256 do original permaneceu
`3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1`.
Não houve instalação de pacotes do sistema, alteração de MCP/configuração global,
redistribuição ou upload de dados do jogo.

## Ferramentas e integridade da imagem

- XenonRecomp `ddd128bcca99fe8bfbb99bea583c972351fa6ace`, submódulos nos commits
  do superprojeto, checkout principal sem modificações rastreadas.
- CMake 3.31.10 extraído de wheel para `.aster/tools/cmake-runtime`; Clang 23.1.1,
  Ninja 1.13.2. Ferramentas locais compiladas: XenonRecomp, XenonAnalyse,
  aster-xex-inspect e aster-recompile-leaf.
- O adaptador gera uma cópia instrumentada de xex.cpp no diretório de build.
  O hook exporta o PE **antes** de o carregador substituir thunks/alterar descritores.
  O fonte upstream permanece intacto. O exportador não inicia código do jogo.
- Fixture original sintética XEX/PE: decodificação comparada byte a byte com o PE
  esperado. O carregamento real retornou 0, dez seções e 14.680.064 bytes.
- O resultado é uma imagem em memória, não um PE em layout de disco. O normalizador
  usa RVA como origem e PointerToRawData como destino; `.text` apresenta offsets
  diferentes nesses campos. PE normalizado: 8.769.024 bytes, SHA-256
  `9c0a403e44bf4d2bbaac43ebdc38619b09a08516a9065241e02cd713ea6dbbec`.
- SizeOfImage do PE: 15.174.656, diferente do tamanho expandido declarado no XEX.
  Todas as regiões inicializadas necessárias foram verificadas dentro dos bytes
  exportados; a diferença não foi ignorada por truncamento/padding arbitrário.

## Análise estática

REA MCP rejeitou XEX e, depois, PE COFF machine 0x01F2. Isso é limitação do
roteamento do REA; não foi apresentada como sucesso. O Ghidra headless 12.1.4
foi usado diretamente com `PowerPC:BE:64:A2ALT-32addr:default`.

Análise concluída em 116 s; log registra Analysis succeeded/Import succeeded.
Inventário exportado: **12.534 funções** reconhecidas pelo analisador, não símbolos
originais recuperados nem garantia de cobertura completa. Entry point observado
em 0x822FC750. Foram exportadas instruções, limites e decompilações de três alvos.

O loader PE genérico emitiu erros/avisos sobre imports, exceptions, TLS, RTTI de
Windows e instruções não resolvidas. Sua interpretação dessas estruturas do Xbox
não foi validada. A linguagem e a região de código foram conferidas; os resultados
estáticos permanecem parciais. Precisaremos de loader/analisadores específicos
para completar as tabelas e melhorar os limites de funções.

Projeto salvo em `build/ghidra/projects/GreenLantern` (Ghidra rejeitou `.aster`
como elemento do caminho de projeto). Preferências/cache/temp redirecionados a
`.aster/ghidra`. Não houve modificação na instalação ou configuração global.

Imports resolvidos independentemente no PE em memória anterior à alteração de
thunks, usando os ordinais das tabelas da revisão fixada do XenonRecomp:
**451 registros, 232 APIs/variáveis distintas, zero nomes não resolvidos**.
Tipos de descritor: 232 do tipo 0 e 219 do tipo 1; os números não são contagens
de chamadas executadas. Os 219 símbolos do carregador não representam os 232
imports únicos. Bibliotecas: xam.xex e xboxkrnl.exe.

XenonAnalyse foi executado e produziu arquivo TOML sem tabelas reconhecidas.
Isso não demonstra que o jogo não tenha switches/chamadas indiretas.

## Experimento de recompilação

Alvo observado: `0x823968F8`, chamado por dez instruções BL diretas no intervalo
principal de código. O Ghidra reconheceu uma função de oito bytes nesse endereço
(`FUN_823968f8`). Sem nome semântico inventado: é um acessor composto por leitura
LWZ no deslocamento 4 do ponteiro recebido e retorno BLR.

O adaptador admite somente essa forma delimitada, verifica a fronteira e solicita
a geração ao XenonRecomp. O C++ resultante foi compilado com Clang para x86_64.
O harness original compara 10.000 palavras com a semântica independente de leitura
big-endian/zero-extension e verifica memória, outro registrador e LR preservados.
Resultado: 10.000 casos aprovados, retorno 0. Não há emulador nem JIT no probe.

Limites: duas instruções, ponteiros válidos alinhados e memória local controlada;
sem MMIO, exceções, concorrência, VMX, gráficos, áudio ou fluxo de inicialização.
Não valida outras funções/instruções. O executável do probe não é o jogo.

Fontes geradas, PE, pseudocódigo e executáveis de teste permanecem em `.aster/`,
ignorados pelo Git. O harness e os scripts rastreáveis são código original.

## Próximo marco técnico

O bloqueio original era **NO_NATIVE_RUNTIME** e **NO_FULL_GAME_BACKEND**. Prioridades
inferidas do inventário real de imports (não de execução observada):

1. Completar loader/análise de funções, helpers e transferências indiretas; validar
   a geração em blocos maiores e registrar instruções não suportadas.
2. Memória/mapeamento e runtime básico: NtAllocateVirtualMemory,
   MmAllocatePhysicalMemoryEx, proteção de páginas e heap.
3. Arquivos, sincronização e threads: NtCreateFile/NtReadFile, ExCreateThread,
   KeWaitForSingleObject e critical sections.
4. GPU Xenos/D3D9: VdInitializeEngines/VdSwap e buffers de comandos; o código de CPU
   traduzido não implementa esse dispositivo.
5. Áudio/XMA/input e serviços XAM, conforme comportamento observado posteriormente.

A comparação inicial com ReXGlue foi realizada no experimento abaixo. O launcher
continua sem backend completo validado; a existência deste executável experimental
não habilita a ação de jogar. Não criar stubs para simular sucesso.

## Ampliação com ReXGlue e estudo dos ports

Os sete projetos indicados pelo usuário foram consultados como referências de
arquitetura, build e diagnóstico; veja [PORT_REFERENCES.md](PORT_REFERENCES.md).
Não foram importados código, patches, arte ou endereços desses jogos.

SDK fixado em v0.10.0, fonte `f5337cdc947ff6d4c4196737e2c807a48f2a1fc2`,
distribuição oficial Linux amd64 com SHA-256 verificado (TOOLING_LICENSES.md).
O projeto gerado fica em `.aster/rex/green-lantern`, sem modificar o SDK.

A primeira análise falhou com 12 UnresolvedCall. Hints da nossa análise foram
registrados em `games/green_lantern_rex_hints.toml`, vinculados ao hash do XEX.
Oito limites concordam com Ghidra/bytes. Quatro são inferidos de fluxo e outras
referências; três absorvem retornos internos nas funções contíguas correspondentes.
Isso não constitui validação semântica desses quatro limites.

Nova análise: retorno 0, **225 arquivos escritos em 21,6 s, sem `--force`**.
A tabela gerada contém 23.386 entradas de mapeamento: não é garantia de cobertura
completa, nem contagem comparável diretamente às 12.534 funções do Ghidra.
Fontes geradas privados: aproximadamente 114 MiB em `.aster/`.

CMake/Clang concluíram as 117 etapas e produziram
`.aster/build/rex-green/aster_green_lantern` (ELF x86_64, aproximadamente 63 MiB).
Foi solicitado `GPU_PLUGINS xenos`. O helper do SDK não copia as bibliotecas do
runtime em Linux: a primeira tentativa terminou no loader com retorno 127.
Corrigido localmente com o helper original
`integrations/rexglue/stage_linux_runtime.cmake`; o build e o `ldd` seguintes
confirmaram resolução de `librexruntimerd.so` e `libTracyClientrd.so` ao lado do host.

Teste limitado a 30 s com `scripts/probe_rex_runtime.py`, sem core dump e com
cache/config/dados do usuário dentro do projeto. Evidências do log:

- SDL escolheu X11; plugin Xenos carregou.
- Vulkan selecionou NVIDIA GeForce RTX 5060 e criou swapchain 1920×1080.
- Runtime registrou `XEX image loaded successfully`.
- A execução alcançou `SetThreadName(6, Main Thread)`.
- Abortou após 2,17 s com SIGABRT (retorno -6), em chamada não registrada
  para **0x822D5D40**. Não houve timeout.

Não foi verificada apresentação de frames do jogo, menus, gameplay, áudio ou input.
Criar swapchain não comprova desenho do jogo. O SDK também reportou chamadas stub
e falhas VFS durante o começo da execução; ainda não sabemos quais são fatais para
o título. Não adicionamos substituições que retornem sucesso artificialmente.

O XEX original manteve o mesmo SHA-256 antes e depois. `game:` foi montado com
`allow_game_relative_writes=false`. Não foram instalados pacotes de sistema.

Relatórios locais: `.aster/reports/rexglue-progress.json`,
`rexglue-runtime-probe.json`, `rexglue-runtime.log` e `rexglue-runtime-stdout.log`.
O próximo alvo de análise é 0x822D5D40: os bytes começam com LIS/ADDI/BLR e depois
padding; não foi recuperado no inventário Ghidra. Seu hint ainda não foi aplicado.
