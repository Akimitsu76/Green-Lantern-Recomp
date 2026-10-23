# Licenças das ferramentas locais

As dependências são baixadas para `.aster/tools`, ignorado pelo Git. Nenhum
executável de ferramentas ou jogo foi empacotado para distribuição. Esta lista
registra os arquivos de licença inspecionados na revisão fixada; não pressupõe
que a licença principal cubra todas as partes transitivas.

| Parte | Evidência local de licença |
|---|---|
| XenonRecomp | MIT, LICENSE.md |
| fmt | MIT, thirdparty/fmt/LICENSE |
| tomlplusplus | MIT, thirdparty/tomlplusplus/LICENSE |
| SIMDe | MIT, thirdparty/simde/COPYING |
| xxHash biblioteca | BSD 2-clause, thirdparty/xxHash/LICENSE |
| tiny-AES-c | Unlicense, thirdparty/tiny-AES-c/unlicense.txt |
| libmspack/lzxd.c | LGPL 2.1, cabeçalho e libmspack/COPYING.LIB |
| disasm/ppc-dis.c | GPL 2 ou posterior, cabeçalho de origem GNU binutils |
| TinySHA1 | Permissão MIT-like no cabeçalho TinySHA1.hpp |
| Tabelas de exports Xbox/XAM | Cabeçalhos de origem Xenia, BSD |
| ReXGlue SDK v0.10.0 | BSD 3-clause, LICENSE; créditos a Xenia preservados |

A distribuição futura das ferramentas vinculadas estaticamente exige tratar as
obrigações GPL/LGPL, fontes e relinkagem aplicáveis; não assumir que tudo é MIT.
O wheel CMake 3.31.10 foi apenas extraído localmente, com seus arquivos de licença
preservados. Seu SHA-256 fixado está em scripts/extract_local_cmake.py.
Não existe autorização de redistribuição de código/PE/assets comerciais do jogo.

ReXGlue foi obtido em fonte na revisão
`f5337cdc947ff6d4c4196737e2c807a48f2a1fc2` e em distribuição oficial Linux amd64
v0.10.0. SHA-256 do ZIP conferido:
`0388edb3f8fb1444f1b0ad5d440cb02d9690ac20a76b04fd6b7dcc19f59328a6`.
O SDK foi extraído localmente, sem instalação ou registro global de pacote CMake.
A licença principal não substitui os avisos das dependências incluídas no SDK.

Os sete ports de referência foram apenas consultados: veja PORT_REFERENCES.md.
Nenhum fonte ou patch desses ports foi incorporado ao projeto.
