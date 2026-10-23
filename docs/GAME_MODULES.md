# Módulos de jogos — API v1

Veja `native_port/modules.py` e `games/green_lantern.py`.

Contrato Python confiável: `api_version`, `id`, `version`, `identify(source)`,
`dependencies()`, `plan(source)`, `build(context)`, `verify(artifact)` e
`launch(artifact)`. Versões incompatíveis são rejeitadas com MODULE_API.

Identidade só é confirmada por execution-info Title ID. O ID 575207E9 vem do
relato Xenia #1803, não de inspeção da ISO local. Hashes/revisões aceitos ainda
não são conhecidos. Não usar nome do arquivo para aceitar um jogo. XEX isolado
não garante assets; o módulo não afirma isso.

O módulo atual descreve etapas futuras como supported=false. Build e verify
retornam NO_NATIVE_BACKEND; launch retorna NOT_READY. `prepare` usa o módulo,
mas a GUI não habilita lançamento. A interface define a fronteira para evolução,
sem prometer um backend já funcional.

Para adicionar jogo, crie módulo confiável em `games/`, implemente identificação,
dependências e plano, e teste passando a instância para `prepare`. Não é preciso
alterar o núcleo. Expor seleção de múltiplos jogos na CLI/GUI ainda é trabalho
pendente: esta versão instancia GreenLantern explicitamente.

Não carregar módulos de dumps ou manifestos externos, nem aceitar strings shell.
O executor de subprocessos é privado à implementação confiável e usa argv;
não fornece sandbox para código Python malicioso. Backend futuro deve usar
operações explícitas, argumentos fixados e paths validados.

Entrada de pasta: o núcleo escolhe default.xex na raiz ou único XEX; registra
manifesto de nomes/tamanhos/mtime, sem declarar assets completos. A API do módulo
recebe os metadados do executável e da pasta. Pastas com vários candidatos sem
default.xex único são rejeitadas, sem tentar executar outro arquivo.

O módulo GreenLantern declara native_probe (hash, endereço, tamanho e harness)
para um experimento limitado já verificado. O adaptador genérico não escolhe um
endereço de outro jogo nem usa esse probe como implementação do runtime.
