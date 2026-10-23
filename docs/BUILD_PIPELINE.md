# Pipeline implementado

`python3 -m native_port prepare pasta-do-jogo` (ou arquivo.xex/ISO) executa:

1. Se for pasta, inventariar arquivos e selecionar XEX; validar cabeçalho e limites
   da entrada, somente leitura. Rejeitar candidatos ambíguos e links internos.
2. Comparar Title ID com o módulo; ISO permanece não identificada nesta etapa.
3. Calcular SHA-256 do executável/ISO em blocos canceláveis; rejeitar alteração
   de tamanho/mtime. Em pasta, incluir também manifesto de nomes/tamanhos/mtime
   na chave de cache; isso não verifica integridade de todos os assets.
4. Consultar dependências e suas versões; registrar ausências.
5. Gerar chave com fonte, API/versão do módulo, configuração e ferramentas.
6. Salvar `.aster/cache/v1/<chave>/report.json` e `.aster/reports/latest.json`.
7. Associar análise existente apenas se SHA-256 de fonte e PE corresponderem.
   Retornar `blocked`, `ready=false`, `artifact=null`; bloqueio atual após análise
   é NO_NATIVE_RUNTIME.

O comando prepare não executa extração, decodificação ou compilação. A análise
e o experimento de função são ações explícitas separadas, descritas abaixo. Uma entrada
inválida encerra o pipeline antes do hash e salva erro estruturado. Logs têm nomes
de tarefas, estados, duração e detalhes do erro. A GUI oferece cancelamento;
processos internos usam grupo separado e são encerrados/recolhidos ao cancelar.
O CLI pode ser interrompido com Ctrl+C (código 130); relatório de cancelamento do
pipeline é garantido para Cancellation, não para término externo/SIGKILL.

O cache é um armazenamento de relatórios; o protótipo recalcula diagnóstico/hash.
Não há cache incremental de compilação ou recuperação de jobs após reinício.

## Utilitário hospedeiro separado

`python3 scripts/host_probe.py` compila scripts/host_probe.cpp com C++17, flags
fixas e sem shell. Captura stdout/stderr (últimos 64 KiB), retorno e duração;
valida magic ELF64 little-endian, tipo executável/PIE, máquina x86_64, permissão e
hash. Executa só esse utilitário e grava `.aster/reports/host-probe.json`.

Isso demonstra a toolchain local. Não recompila nenhuma instrução PowerPC, não
valida assinaturas do jogo e não constitui um runtime. O CMakeLists opcional expõe
a mesma ferramenta e CTest. Agora o CMake local configurou e compilou esse alvo;
CTest não foi executado separadamente.

Um backend futuro precisará fornecer funções identificadas, tradução de CPU,
runtime e verificação do jogo; uma simples validação ELF nunca será suficiente
para habilitar o botão de iniciar.

## Ferramentas e experimento nativo local

Revisão do XenonRecomp e submódulos: XENONRECOMP_EVALUATION.md.
Para reconstituir ferramentas em um checkout novo, baixar o superprojeto e seus
submódulos nos commits fixados, fazer download do wheel pinado com pip download
(não pip install) e executar scripts/extract_local_cmake.py. Nenhum script externo
baixado deve ser executado sem revisão.

```sh
git clone https://github.com/hedge-dev/XenonRecomp.git .aster/tools/XenonRecomp
git -C .aster/tools/XenonRecomp checkout ddd128bcca99fe8bfbb99bea583c972351fa6ace
git -C .aster/tools/XenonRecomp submodule update --init
python3 -m pip download --only-binary=:all: --no-deps --no-cache-dir --dest .aster/tools/downloads cmake==3.31.10
python3 scripts/extract_local_cmake.py
python3 scripts/build_xenon.py
python3 scripts/make_xenon_fixture.py
python3 scripts/analyze_xex.py '/caminho/pasta-do-jogo' --allow-decode
python3 scripts/analyze_ghidra.py --inspect-address 0x823968F8
python3 scripts/analyze_xex.py '/caminho/pasta-do-jogo' --allow-decode --probe
```

O último comando requer análise Ghidra prévia para confirmar a fronteira da função;
sem --probe executa somente decodificação/normalização/imports. O probe aceita
apenas a revisão de dump declarada no módulo GreenLantern e nunca inicia o jogo.
A autorização explícita --allow-decode é obrigatória para entrada criptografada.
O launcher Preparar apenas lê resultados já existentes; não decodifica implicitamente.

Logs, argumentos, stdout/stderr limitados a 64 KiB, códigos, duração e hashes:
`.aster/reports/xenon-build.json` e `.aster/reports/xenon-analysis.json`.
Ghidra usa scripts/ghidra com processor PowerPC:BE:64:A2ALT-32addr e projeto em
build/ghidra/projects, com configurações/cache em .aster/ghidra.
O comando de importação requer -postScript ExportPortAnalysis.java OUTPUT_JSON
0x822FC750 para o hash analisado. Não reutilizar esse endereço para outro dump.

Normalização mantém o PE original decodificado e reconstrói os offsets de arquivo
em uma cópia. Código gerado e derivados do jogo nunca saem de .aster/.

`scripts/analyze_ghidra.py` calcula a entrada a partir do PE, confere o hash MD5
reportado pelo programa Ghidra e a linguagem, redireciona configuração/cache/temp
ao projeto e salva logs/duração em reports/ghidra-run.json. O projeto padrão usa
prefixo derivado do SHA-256. Para o projeto inicial preservado nesta sessão:

```sh
python3 scripts/analyze_ghidra.py --reuse --project-name GreenLantern --inspect-address 0x823968F8
```

Não usar esses endereços de inspeção para outro hash. `--reuse` é somente leitura
sobre o projeto Ghidra e não repete autoanálise. Os exemplos com endereços são
específicos do dump registrado no módulo GreenLantern.
