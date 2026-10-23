# Componentes públicos

O launcher Aster Native não inclui conteúdo do jogo. O código específico do
dump é produzido somente no computador do usuário e não faz parte do pacote.

Os pacotes portáteis incluem Python (licença PSF), Tcl/Tk (licença Tcl/Tk),
PyInstaller (GPL com exceção para o bootloader), CMake (BSD) e Ninja (Apache 2.0).
As licenças fornecidas pelos componentes são copiadas para `LICENSES` no pacote.
O Python Linux é proveniente de `astral-sh/python-build-standalone`; o Python
Windows é o instalador oficial de python.org, preparado em prefixo Wine isolado.

O AppImage também inclui o runtime oficial `AppImage/type2-runtime`.
Seu aviso de licença acompanha os recursos em `LICENSES/AppImage-runtime-LICENSE`.
O appimagetool é usado apenas para empacotar, sem ser incorporado ao launcher.

ReXGlue SDK 0.10.0 é baixado separadamente do release oficial
https://github.com/rexglue/rexglue-sdk/releases/tag/v0.10.0, com hashes fixados.
O SDK e os derivados Xenia usam a licença BSD indicada em seu arquivo LICENSE.
O patch público de cache mantém os avisos originais nas fontes baixadas.
glslang também é baixado em commit fixado para fornecer headers compatíveis.
As licenças desses componentes permanecem nas respectivas árvores do SDK.

Os nomes Green Lantern e Rise of the Manhunters identificam o jogo compatível;
este launcher experimental não é uma distribuição do jogo nem uma versão
oficial. É necessário fornecer os próprios arquivos do dump suportado.
