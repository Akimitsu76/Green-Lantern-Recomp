# Gerar o port no seu PC

O pacote contém o launcher, Python/Tk e as ferramentas portáteis CMake/Ninja.
Não contém o jogo, saves, shaders extraídos, código recompilado ou executável
do jogo. O port é gerado **localmente a partir do seu dump**.

## Compatibilidade

- Linux x86-64 com glibc >=2.34, driver Vulkan e fragment shader interlock.
  O launcher usa Python portátil; o SDK oficial tem requisitos adicionais de
  C++23/libstdc++. Outras distribuições e GPUs ainda precisam de validação.
- Windows 10/11 x64: o launcher é um `.exe` com Python/Tk embutidos. O gerador
  usa o SDK Windows e D3D12/ROV. A interface foi testada via Wine; a compilação
  e execução **do jogo no Windows real ainda não foram validadas**.
- Uma toolchain Clang >=18 com biblioteca padrão C++23 é necessária para gerar
  o jogo. No Linux, instale Clang e headers/bibliotecas de desenvolvimento C/C++
  da distribuição. No Windows, instale Visual Studio Build Tools 2022 com
  desenvolvimento C++ x64, Windows SDK e Clang. O launcher procura `vswhere`
  e carrega o ambiente x64 automaticamente quando disponível.
- O único XEX validado atualmente tem SHA-256
  `3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1`.
  Outra revisão é rejeitada antes de baixar ferramentas ou gerar código.

## Primeiro uso

### Arquivo único (recomendado)

Baixe `AsterNative-windows-x64.exe` ou `AsterNative-linux-x86_64.AppImage`.
O `.exe` abre diretamente. No Linux, dê permissão de execução ao AppImage e
abra-o. Não é necessário extrair um ZIP nem manter pastas ao lado do arquivo.
O AppImage usa FUSE; se o sistema não o oferecer, execute
`./AsterNative-linux-x86_64.AppImage --appimage-extract-and-run`.

Os recursos públicos são instalados automaticamente na pasta de dados do usuário:
`%LOCALAPPDATA%/AsterNative/app` no Windows e
`${XDG_DATA_HOME:-~/.local/share}/aster-native/app` no Linux.
Builds, downloads, preferências e saves ficam em `.aster` dentro dessa pasta,
preservados entre aberturas e atualizações. Mover o arquivo baixado não apaga os
dados. O primeiro uso e a geração precisam de espaço livre nessa pasta.
Os requisitos de Clang/C++23 e do dump continuam os mesmos.

### Pacotes em pasta (formato anterior)

1. Extraia **toda** a pasta `AsterNative` do ZIP (Windows) ou TAR.GZ (Linux)
   em um local gravável. Mantenha `app` e `_internal` ao lado do executável.
2. Abra `AsterNative.exe` no Windows ou `AsterNative` no Linux. Não é necessário
   instalar Python nem rodar pip para usar o launcher.
3. Selecione a pasta extraída que contém `default.xex` e os demais arquivos do
   jogo. ISO e XEX isolado não são suficientes para esta geração.
4. Clique **GERAR PORT NATIVO**, ou abra a página **Gerar port**.
5. Confirme o download das ferramentas oficiais fixadas. Windows: SDK de cerca
   de 43 MB; Linux: SDK de 116 MB e até 55 MB de fontes públicas adicionais
   para reproduzir o patch de cache persistente. Os downloads são verificados
   por SHA-256. Nenhuma ferramenta é instalada globalmente.
6. Acompanhe **Gerar port**. As seis etapas mostram downloads em bytes, compilação
   em alvos Ninja e atividade indeterminada quando não existe um total conhecido.
   O launcher verifica o dump, gera C++ pelo ReXGlue,
   configura CMake e compila. Não feche o launcher durante a geração; para
   interromper use **Cancelar tarefa**. Logs ficam em `app/.aster/native/`.
7. Após **Port gerado**, clique **JOGAR AGORA**. Compilação concluída não é
   certificação de gameplay: inicialização, áudio e campanha devem ser testados.

O dump é lido sem alterações. Todos os alvos de FPS e configurações gráficas
compartilham saves e cache em `.aster/runtime/green-lantern/` na pasta de dados
do usuário do sistema. O perfil de 30 FPS já existente continua como principal.
Pastas antigas de 60 FPS/ilimitado são preservadas, sem sobrescrever progresso.

## Compilação incremental

O build é identificado pelo hash do XEX, versão do SDK, plataforma, hints e hook.
Ao repetir **Gerar port**, os hashes dos artefatos são conferidos. Um build
íntegro é reutilizado sem rodar codegen ou compilador. Builds incompletos mantêm
seus objetos para o Ninja continuar. Novas receitas usam outra pasta; builds
anteriores e seus logs são preservados. O registro fica em
`app/.aster/config/native-install.json`.

O perfil de compilação usa `RelWithDebInfo` para corresponder ao SDK/runtime.
O controle legado de tipo de build da inspeção não altera esse contrato de ABI.
No Linux o plugin Vulkan com cache de driver é compilado contra o SDK fixado;
não é substituído pelo plugin original no staging final.

## Gráficos e FPS

30 FPS continua padrão. 60 e ilimitado são experimentais e pedem confirmação.
Ilimitado remove a espera da engine; não é renderização independente de uma
simulação fixada em 60 atualizações/s. Gameplay, física e áudio desse modo não
estão certificados.

No Linux, desligar VSync seleciona apresentação imediata e preserva o relógio
guest de 60 Hz. Assim os limites de 30/60 continuam funcionando. No Windows,
o caminho usa o presenter D3D12; comportamento visual ainda precisa de teste
nativo. O MSAA é controlado pelo jogo/backend: o launcher não anuncia um falso
botão para desligá-lo. “Cache de texturas” altera orçamento de memória, não a
resolução dos arquivos de textura.

A opção **Resolução da janela** inclui **1920x1080 (Full HD)**. Ela controla
a saída; a renderização interna permanece em 1x (720p). Os testes reproduziram
áreas pretas com escala interna 2x tanto em 30 quanto em 60 FPS. Por segurança,
o launcher e o comando de jogo usam 1x, inclusive ao carregar preferências antigas.
Isso contorna o defeito; a renderização interna em 2x/3x ainda precisa de correção.

Shaders e pipelines já conhecidos são preparados na inicialização. Novos shaders
compilam em segundo plano no modo `async`; o primeiro encontro ainda pode causar
engasgos. O cache persistente é comum a todos os alvos de FPS.

## Pelo terminal

```sh
# No código-fonte:
python3 -m native_port build /caminho/Green_Lantern --download-sdk --jobs 2
python3 scripts/play_green_lantern.py /caminho/Green_Lantern --validar

# No pacote Linux:
./AsterNative build /caminho/Green_Lantern --download-sdk --jobs 2
./AsterNative gui
```

No Windows, substitua `./AsterNative` por `AsterNative.exe` e informe o caminho
do dump entre aspas. O primeiro build pode demorar e consumir bastante RAM/disco;
comece com uma ou duas tarefas paralelas.

## Empacotar o launcher

Use Python/PyInstaller da plataforma de destino. O script
`scripts/package_launcher.py` aceita `--cmake-data` e `--ninja` para incluir as
ferramentas portáteis e produz os arquivos em `dist/`. O pacote Linux é gerado
com Python standalone e Ninja manylinux, evitando depender da glibc 2.44 desta
máquina de desenvolvimento. Para Windows foi usado Python Windows sob Wine;
isso testa o launcher, não substitui testes do jogo em um PC Windows.

A distribuição usa uma lista explícita de fontes/recursos públicos. `.aster`,
dumps e gamecode gerado nunca entram no pacote. `PACKAGE.json` contém os hashes
dos arquivos distribuídos. Consulte `LICENSES` e `THIRD_PARTY_NOTICES.md`.
