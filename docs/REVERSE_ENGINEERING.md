# Engenharia reversa e evidências

**Atualização posterior à autorização:** decodificação, análise Ghidra e recompilação
de uma função real concluídas. Veja [NATIVE_PROGRESS.md](NATIVE_PROGRESS.md) para
resultados atuais e limitações. A avaliação inicial abaixo permanece histórica.


## Atualização: XEX real

Metadados do default.xex fornecido pelo usuário foram lidos sem descriptografia:
Title ID 575207E9, base declarada 0x82000000, entrada declarada 0x822FC750,
criptografia normal e compressão basic. Imports xam.xex/xboxkrnl.exe inventariados
sem resolver ordinais. REA rejeitou importação direta do XEX. Detalhes, hash e
limitações em [XENONRECOMP_EVALUATION.md](XENONRECOMP_EVALUATION.md).
O código do jogo não foi descompilado ou analisado.

## Sessão inicial

REA MCP 6.7.0 acessível; `binary_session({})` retornou provider Ghidra disponível.
Ghidra 12.1.4 usa Java 21 e decompilador linux_x86_64. Nenhum binário do jogo foi
aberto, descompilado ou analisado. Não há funções, símbolos ou imports confirmados.
Relatório local: `.aster/reports/rea-session.json`.

A ISO tem 7.838.695.424 bytes. Foram lidos somente cabeçalhos e, depois, feita
busca completa por assinaturas usando mmap ACCESS_READ. Sem XDVDFS/CD001.
Duas ocorrências de XEX2 foram encontradas na varredura reproduzível; nenhuma
contém cabeçalho coerente. Nenhum candidato foi
extraído nem importado como código. A extensão do arquivo não prova seu formato.

`scripts/survey_image.py` reproduz busca e SHA-256 em streaming, armazena apenas
metadados no relatório local e não altera a imagem. Consulte o resultado executado
em `.aster/reports/image-survey.json`; as posições não são endereços de funções.

## Procedimento quando houver entrada utilizável

1. Registrar caminho, tamanho, SHA-256, revisão e origem fornecida pelo usuário.
2. Validar volume e extrair arquivo principal/assets para workspace; confirmar
   membros e impedir nomes absolutos, travessia de diretório e symlinks de saída.
3. Validar XEX2/segurança/opcionais. Proteção não disponível é um bloqueio explícito.
4. Confirmar loader instalado e compatível com Ghidra; não importar como raw
   escolhendo arquitetura ou endereços arbitrariamente.
5. Verificar `PowerPC:BE:64:A2ALT-32addr` conforme especificação do loader e
   coerência da entrada, regiões de memória e instruções. PPC usa registradores
   de 64 bits e espaço de endereçamento do título de 32 bits.
6. Esperar a análise concluir antes de declarar resultados. Registrar hashes,
   versão das ferramentas, endereço, evidência e limitações em cada observação.
7. Inventariar imports, funções e referências, distinguir wrappers de APIs e
   engine somente com evidência. Preservar projeto e relatórios necessários, pois
   a base efêmera do provider REA é descartada ao fechar.

Não há assets, dumps, chaves ou código proprietário incorporados ao repositório.
