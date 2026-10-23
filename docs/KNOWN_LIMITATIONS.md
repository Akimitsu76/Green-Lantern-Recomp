# Limitações atuais — atualização v0.1.2

- Projeto experimental; campanha completa e compatibilidade ampla não certificadas.
- 30 FPS é padrão; 60 FPS/ilimitado continuam experimentais. Saves pertencem ao usuário e são compartilhados entre configurações.
- Renderização interna fixada em 720p para evitar os artefatos vistos com supersampling. Resolução de janela e ampliação não acrescentam detalhes de textura.
- Ampliação bicúbica/nitidez e o novo backend Vulkan são específicos do Linux x86-64 com SDK fixado. Windows usa bilinear; o jogo em Windows real não foi validado.
- Shaders conhecidos são reutilizados. Shaders novos, pipelines com memexport e retenção de quadros completos ainda podem causar pausas. Não há garantia de zero stutter.
- A validação recente cobre o início da missão 1, movimento e combate; não certifica todo o jogo, áudio, todas as sombras nem todas as GPUs.
- O launcher exige dump completo da revisão suportada e toolchain C++ local. Não contém jogo, assets, saves ou código recompilado do jogo.
- Os executáveis não são assinados.

Consulte VALIDATION.md e SPATIAL_FILTER.md para evidências e detalhes.
