# Green Lantern Recomp — Aster Native

Port experimental de **Green Lantern: Rise of the Manhunters (Xbox 360)** para
PC, com launcher portátil e geração local baseada em ReXGlue.

**O launcher não é o jogo.** O executável distribuído abre a interface, valida o
seu dump, baixa ferramentas oficiais fixadas e gera/compila o host nativo no seu
computador. Nenhum arquivo do jogo ou código recompilado a partir dele é
distribuído neste repositório.

> Estado: **experimental**. A inicialização e o começo da missão 1 têm evidência
> no Linux; campanha completa, Windows real, outras GPUs e áudio ainda não estão
> certificados. Leia as limitações antes de baixar.

## Downloads

As releases oferecem arquivos únicos. A atualização experimental **v0.1.2** está preparada localmente; os links abaixo apontam para a página de downloads publicados:

- [Windows x64 — AsterNative-windows-x64.exe](https://github.com/Akimitsu76/Green-Lantern-Recomp/releases)
- [Linux x86-64 — AsterNative-linux-x86_64.AppImage](https://github.com/Akimitsu76/Green-Lantern-Recomp/releases)
- [SHA-256 dos downloads](https://github.com/Akimitsu76/Green-Lantern-Recomp/releases)
- [Página da release](https://github.com/Akimitsu76/Green-Lantern-Recomp/releases)

Os antigos pacotes em pasta (`.zip`/`.tar.gz`) são formatos anteriores e não são
necessários para este fluxo. Não é preciso instalar Python nem manter
`app`/`_internal` ao lado do arquivo baixado.

## Requisitos

Para **abrir o launcher**, não é necessário instalar Python. Os arquivos únicos
incluem Python/Tk, CMake e Ninja.

Para **gerar o jogo**, ainda são necessários:

- dump próprio extraído, contendo `default.xex` **e os demais arquivos do jogo**;
- Clang >=18 com biblioteca padrão C++23 e ambiente de desenvolvimento C/C++;
- no Windows: Visual Studio Build Tools com C++ x64, Windows SDK e Clang;
- no Linux: toolchain Clang, headers/bibliotecas de desenvolvimento, driver
  Vulkan e suporte ao caminho de fragment shader interlock (FSI) usado pelo host;
- espaço livre em disco e acesso aos downloads oficiais no primeiro uso;
- sistema **x86-64**. Outras arquiteturas não são suportadas.

ISO ou um `default.xex` isolado não bastam para esta geração. O launcher precisa
da pasta extraída completa.

## Revisão suportada

Apenas esta revisão de `default.xex` é aceita atualmente:

```text
SHA-256: 3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1
```

Outra revisão é rejeitada antes de baixar ferramentas ou gerar código. Não há
suporte anunciado a outras revisões, ISOs ou XEX isolados.

## Primeiro uso

1. Baixe o arquivo da sua plataforma na release.
2. **Windows:** abra `AsterNative-windows-x64.exe`. O arquivo não é assinado
   digitalmente; o SmartScreen pode pedir confirmação. Não é necessário extrair
   nada.
3. **Linux:** marque o AppImage como executável e abra-o:
   ```sh
   chmod +x AsterNative-linux-x86_64.AppImage
   ./AsterNative-linux-x86_64.AppImage
   ```
   Se o sistema não tiver FUSE, use:
   ```sh
   APPIMAGE_EXTRACT_AND_RUN=1 ./AsterNative-linux-x86_64.AppImage
   ```
4. No launcher, selecione a pasta extraída que contém `default.xex` e os demais
   arquivos. Confirme o download das ferramentas oficiais e clique em
   **Gerar port nativo**. A primeira geração pode demorar e consumir bastante
   RAM/disco.
5. Quando o build estiver íntegro, use **Jogar agora**. O launcher valida dump,
   build, plugin e referência FSI antes de abrir.

### Dados persistentes

Os recursos públicos são instalados automaticamente na pasta de dados do
usuário; o arquivo baixado pode ser movido ou atualizado sem apagar builds,
preferências ou saves:

- Windows: `%LOCALAPPDATA%/AsterNative/app`
- Linux: `${XDG_DATA_HOME:-$HOME/.local/share}/aster-native/app`

Builds, downloads, configurações e perfis ficam em `.aster` dentro dessa pasta.
Para usar outra pasta de dados, defina `ASTER_DATA_HOME`. A pasta temporária de
extração do PyInstaller/AppImage não é usada para dados permanentes.

## Atualização gráfica experimental

No Linux, pipelines Vulkan novos podem ser preparados em segundo plano. Pipelines com escrita de memória permanecem síncronos por correção; a retenção de quadro completo e o primeiro encontro com shaders ainda podem causar pausas. O cache conhecido é reutilizado e preparado antes da partida. Não há promessa de ausência total de engasgos.

A saída oferece 1920×1080, 1440p e 4K; a renderização interna permanece em 1280×720. No Linux, Alta usa ampliação bicúbica e Ultra acrescenta nitidez; no Windows ambos usam bilinear e mantêm as diferenças de filtragem anisotrópica/cache. Cache maior não adiciona texturas HD. Veja [SPATIAL_FILTER.md](docs/SPATIAL_FILTER.md).

## Estado e limitações

- **Linux:** geração completa pelo AppImage, abertura da interface, arquivo
  copiado/renomeado, workers empacotados, geração do port e reutilização de
  build íntegro foram exercitados. A inicialização e o começo da missão 1 têm
  evidência anterior; a campanha completa não foi concluída.
- **Windows:** o launcher `.exe` foi aberto e testado via Wine. A compilação e a
  execução **do jogo em Windows real não foram validadas**. Não trate o host
  Windows como certificado.
- **Gráficos/FPS:** 30 FPS é o padrão. 60 FPS e ilimitado são experimentais,
  pedem confirmação e compartilham o save da pasta do usuário. As medições anteriores de 30/60 na
  tela inicial eram de apresentação; não são certificação de FPS durante toda a
  jogabilidade. Física, animações e áudio em alvos elevados não estão
  integralmente corrigidos nem certificados.
- **Hardware:** compatibilidade ampla com outras GPUs e distribuições Linux não
  foi validada. O caminho Linux usa Vulkan/FSI e depende do driver.
- **Conteúdo:** nenhum dump, asset, shader extraído, save ou código recompilado
  do jogo é publicado. Você precisa fornecer seus próprios arquivos.
- Os executáveis não são assinados digitalmente.

## Testes e validação

A última regressão local executou **176 testes** em Xvfb 1440×900; todos passaram,
sem falhas e sem skips. Ela cobre o launcher Tk, presets/CVars, saves compartilhados, validação de destinos,
empacotamento, persistência de dados, extração segura do payload e caminhos dos
workers. Três testes de integração que dependem de artefatos gerados localmente
são pulados automaticamente em um checkout limpo; esses artefatos não fazem
parte do repositório.

A geração completa do port pelo AppImage usou arquivos oficiais já baixados e
verificados por hash. Isso não é um teste novo dos downloads pela rede.

Consulte [VALIDATION.md](docs/VALIDATION.md) para o histórico e
[KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) para os limites atuais.
Documentos históricos podem citar contagens de testes de etapas anteriores.

## Desenvolvimento

Requisitos para rodar a partir do código: Python >=3.11 e Tkinter/Tk. O núcleo
não tem dependências pip obrigatórias. Para o utilitário C++ opcional, um
compilador C++17.

```sh
python3 -m native_port doctor
python3 -m native_port gui
python3 -m native_port build "/caminho/da/pasta-do-jogo" --download-sdk --jobs 2
python3 scripts/play_green_lantern.py "/caminho/da/pasta-do-jogo" --validar
```

Testes:

```sh
xvfb-run -a -s '-screen 0 1440x900x24' python3 -m unittest discover -s tests -q
```

O histórico de investigação está em
[PROJECT_HISTORY.md](docs/PROJECT_HISTORY.md). Guias úteis:
[PORTABLE_BUILD.md](docs/PORTABLE_BUILD.md),
[SINGLE_FILE_RELEASE.md](docs/SINGLE_FILE_RELEASE.md),
[ARCHITECTURE.md](docs/ARCHITECTURE.md),
[GRAPHICS_PRESETS.md](docs/GRAPHICS_PRESETS.md) e
[DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Componentes de terceiros e licenciamento

O projeto usa componentes públicos, incluindo ReXGlue/Xenia (BSD), Python (PSF),
Tcl/Tk, PyInstaller, CMake (BSD), Ninja (Apache 2.0) e o runtime do AppImage. Os
avisos e licenças aplicáveis estão em
[THIRD_PARTY_NOTICES.md](docs/THIRD_PARTY_NOTICES.md) e
[TOOLING_LICENSES.md](docs/TOOLING_LICENSES.md). O código original deste
repositório não tem uma licença de redistribuição declarada; os componentes de
terceiros mantêm suas próprias licenças.

Green Lantern e Rise of the Manhunters identificam o jogo compatível. Este é um
projeto experimental independente, não afiliado aos titulares da propriedade
intelectual, e não distribui o jogo.
