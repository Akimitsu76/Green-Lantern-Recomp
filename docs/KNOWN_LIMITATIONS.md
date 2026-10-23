# Limitações conhecidas

- O backend nativo próprio do Aster Native continua sem runtime completo,
  renderização, áudio, controles ou gameplay implementados. O host experimental
  ReXGlue recompilado abre menus e o começo da missão 1; não é um port completo
  nem valida a campanha. Veja PLAYABILITY.md.
- A função de oito bytes recompilada/executada como experimento não valida o
  restante do jogo. O host ReXGlue usa código recompilado e hints; veja
  NATIVE_PROGRESS.md, XENONRECOMP_EVALUATION.md e PLAYABILITY.md.
- XEX decodificado após autorização. O original permanece intacto; os derivados
  privados ficam em `.aster/`. A antiga ISO continua sem formato reconhecido.
- REA MCP rejeita XEX e PE PowerPCBE. Ghidra direto funciona com linguagem explícita,
  mas loader PE genérico tem limitações de imports/exceptions/TLS/RTTI e VMX.
- Contagem de funções do analisador não prova cobertura completa nem nomes originais.
  Nenhuma tabela reconhecida pelo XenonAnalyse não significa ausência de indireções.
- Validadores verificam limites/estrutura, sem autenticar assinaturas criptográficas,
  mídia completa, integridade de todos os assets ou equivalência integral de CPU.
- O hash de um dump foi analisado; não há catálogo de revisões compatíveis.
- CMake e XenonRecomp locais estão disponíveis. Builds locais foram executados sem
  instalar pacotes do sistema. Dependências e obrigações de distribuição constam
  de TOOLING_LICENSES.md. Nenhum redistribuível completo foi criado.
- Relatórios de análise só são associados ao mesmo hash de origem e PE normalizado
  correspondente. Compilação C++ usa incremento do Ninja; relatórios de preparação
  continuam recalculando hash/diagnóstico. Não há retomada automática de jobs.
- A GUI usa **Gerar port nativo** para produzir o host ReXGlue e **Jogar agora**
  para abrir o build local validado. Os controles do backend nativo próprio do
  Aster continuam desabilitados. Os alvos 30/60/ilimitado e os presets
  Baixa/Padrão/Alta/Ultra/Personalizada ficam na aba **Gráficos**. 60 e
  ilimitado são opt-in, com confirmação e perfis isolados; 30 fps continua o
  padrão. Preparar mostra análise validada e experimento nativo quando
  pertencem ao mesmo dump; não inicia o probe.
- Sessão humana 058 confirmou gameplay/combate visual em 60 fps, mas teve 6
  janelas de 5 s abaixo de 59 apresentações/s (3 abaixo de 55), incluindo uma
  queda de 822 ms em transição. A percepção desses engasgos e a qualidade de
  física, animações e áudio continuam sem certificação; a sessão não mediu áudio.
- O modo ilimitado v10 tem apenas evidência automatizada: 90,16 s, 38.627
  apresentações, FSI, simulação em alvo 60/tempo real e nenhum fatal. O probe
  registra `gameplay_verified=false`; não há captura visual de gameplay no
  Xwayland. Tearing, estabilidade, áudio e comportamento de combate/física
  continuam sem validação humana. A GPU observada foi 95–96% e ~91–107 W.
- Os presets Baixa/Alta/Ultra não têm avaliação visual humana pareada nem
  medição de VRAM/desempenho em outras GPUs. 2x/3x aumentam a resolução interna
  e podem reduzir bastante o FPS; o preset Padrão é o único com histórico de
  uso principal.
- O launcher só habilita **Jogar agora** para o mesmo dump identificado e para
  builds/referências FSI presentes em `.aster/`. Não há suporte genérico a
  outras revisões do dump nem redistribuição de assets/código proprietário.
- Pasta é limitada a 100.000 arquivos e 32 níveis; links internos são rejeitados.
  Manifesto de assets usa nomes/tamanhos/mtime; completude não certificada.
- As execuções experimentais podem deixar arenas `xenia_memory_*` em `/dev/shm`
  porque o runtime usa `_Exit`. A limpeza exige auditoria de inode/mapas e
  autorização explícita; não limpar `/dev/shm` genericamente.
- Isolamento de caminhos pressupõe uso local confiável; não fornece sandbox contra
  outro processo malicioso alterando symlinks em corrida.

Próximo marco: ampliar geração/análise e validar a compilação experimental
(combate, física, áudio, campanha e outras GPUs) antes de tratar o backend como
completo. Não simular sucesso de serviços ausentes para habilitar execução.
