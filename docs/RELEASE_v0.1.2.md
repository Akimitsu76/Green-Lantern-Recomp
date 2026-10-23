# v0.1.2 — gráficos e preparação de shaders (experimental)

- Linux: preparação de pipelines Vulkan em segundo plano e reutilização de cache conhecido; pipelines com memexport continuam síncronos.
- Alta/Ultra no Linux: ampliação bicúbica e nitidez opcionais, mantendo o render interno 720p para evitar artefatos de supersampling.
- Saída 1920×1080 e saves compartilhados entre 30/60 FPS e presets, separados por pasta de usuário.
- Launcher atualizado para Linux e Windows; no Windows os presets usam bilinear. Jogo em Windows real ainda não validado.
- Reutilização de CPU verificada em atualizações apenas do backend gráfico e ajuste de ciclo de vida das arenas compartilhadas Linux.

Validação: 176 testes passaram; sessões curtas de movimento/combate na missão 1 em Linux. A campanha completa não foi validada. Shaders novos ainda podem causar pausas; não há promessa de zero stutter ou de texturas HD.

Baixe o AppImage no Linux ou o .exe no Windows. Confira SHA256SUMS. É necessário um dump próprio completo da revisão suportada e uma toolchain C++ para gerar o port localmente.
