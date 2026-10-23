# Revisão da continuação pelo OpenCode — 22/10/2026

Os testes posteriores e os polimentos estão em [PLAYABILITY.md](PLAYABILITY.md).
O confronto após os primeiros destroços foi alcançado, há sinal de áudio medido
no stream do jogo, e o launcher passou a abrir a sessão experimental.
As seções abaixo preservam a revisão e suas evidências por etapa.

## Progresso comprovado

O teste histórico `011-stable-60s` permaneceu ativo até o limite de 60 s e
alcançou a tela de título **Press START**, confirmada visualmente na captura
privada `window-14.png`. Isso vai além da tela de copyright vista antes da pausa.
Não comprova gameplay, áudio correto, saves ou compatibilidade completa.

O OpenCode acrescentou ferramentas de análise `.pdata`/CFG e mesclagem de hints,
três hints individuais e um lote de 1.851 entradas. O SDK upstream permaneceu
sem modificações rastreadas. Não existe commit-base do projeto que permita
atribuir todas as diferenças a um autor; a revisão comparou os arquivos atuais
com o checkpoint e as evidências existentes.

## Problemas corrigidos

- O probe usava uma chamada PRESENT como critério de `ready=true`. Corrigido:
  apresentação e jogabilidade são campos diferentes; `ready` permanece falso.
- Leitura e ordem dos logs rotacionados corrigidas. A reavaliação independente
  do teste 011 encontrou **2.391 chamadas PRESENT retidas**, em vez da única
  chamada registrada no resumo antigo. São chamadas observadas, não frames
  visualmente validados. Os relatórios históricos foram preservados.
- O analisador aceitava função truncada ao encontrar instrução desconhecida.
  Agora rejeita o candidato se um caminho alcançável não possui saída comprovada.
  Isso inclui limites do Capstone em instruções específicas do Xenon/VMX128.
- `bctrl`/`blrl` eram tratados como retornos; agora chamadas com LK possuem
  continuação. Destinos diretos consideram os bits AA/LK corretamente.
- A verificação de stack concatenava caminhos incompatíveis. Agora propaga
  deltas de r1 no CFG, exige restauração em cada saída e rejeita escritas
  desconhecidas/estados conflitantes. Isso prova apenas o delta da stack.
- A CLI de inspeção falhava sem `--address`; passou a salvar relatório agregado.
  `--no-write` também impede a escrita de lote TOML.
- A mesclagem agora exige identidade PE correspondente e limita tamanhos;
  reaplicação sem entradas novas não acrescenta blocos vazios.
- Leituras guest agora precisam caber nos bytes físicos da própria seção,
  sem interpretar bytes de outra seção como memória virtual não inicializada.

## Revisão do lote e limites

Das 1.851 entradas do lote, 1.826 mantiveram exatamente o mesmo limite segundo
o analisador corrigido. Outras quatro são ajustadores ADDI/B completos, conferidos
separadamente, com destino já registrado. **21 entradas ficaram em quarentena.**
As 53 entradas anteriores foram preservadas: **1.883 hints** após a revisão.
Depois foi recuperado mais um destino observado em execução: `0x8220D2D0`,
uma tail branch de quatro bytes para `0x82201590`, seguida de padding. Total
atual: **1.884 hints**.

Quarentena não significa que a função não existe: significa que o limite
anterior não foi comprovado. Não reduzimos erros usando `--force` ou retornos
artificiais. O original do lote e as razões individuais estão privados em:

- `.aster/analysis/green-lantern/opencode-hints-before-review.toml`
- `.aster/analysis/green-lantern/opencode-hints-review.json`
- `.aster/reports/opencode-runtime-reassessment.json`

Os testes passaram: **102 testes, sem falhas ou skips no Xvfb**, incluindo regressões de função
truncada, chamada indireta, stack por caminho, AA/LK e classificação dos logs.
O host foi recompilado com o lote revisado. Novos testes de execução recebem
labels a partir de `012-reviewed-menu-input`; consulte os relatórios reais.

## Continuação da validação

O probe aceita `--keyboard` para habilitar a implementação MnK existente no SDK
e ações explícitas `--press SEGUNDOS:TECLA`. Eventos são enviados exclusivamente
à janela cujo PID corresponda ao processo iniciado; não são enviados à raiz ou
ao desktop. Uma ação enviada não comprova que o jogo a processou: isso deve ser
conferido nas capturas e no comportamento posterior.

Os testes 012–015 confirmaram resposta ao START/A, navegação com W (stick esquerdo),
criação de `GL_10` dentro de `.aster/runtime/green-lantern/user` e enumeração/leitura
desse perfil após reiniciar o processo. O teste 015 exibiu a abertura após carregar
uma partida. Isso valida o perfil inicial, não um save de campanha completo.

O teste 016 abortou em 0x8220D2D0 durante a transição da abertura/entrada START;
o teste 017, após a recuperação, alcançou mundo e HUD da primeira fase e foi
encerrado pelo limite de 150 s, sem fatal registrado. A geometria aparece em
grande parte preta. Há comparação de opções gráficas em andamento a partir do
teste 018; não declarar o problema resolvido sem conferir as capturas.

## Resultado da comparação gráfica

O teste 018 ativou apenas `gpu_allow_invalid_fetch_constants`: o personagem do
menu continuou preto. O teste 019 alterou apenas `render_target_path_vulkan=fsi`
em relação ao padrão, sem permitir os fetches inválidos, e o personagem passou
a aparecer com textura e iluminação. O código do SDK descreve FSI como caminho
de maior precisão para packing/blending/depth em EDRAM. Isso é uma correção de
compatibilidade pelo backend existente, não um renderizador novo do projeto.

O teste 020 confirmou cenário, personagem, inimigos e HUD da primeira fase com
FSI durante 140 s, sem fatal registrado. O teste 021 enviou W/D por dois segundos
e ações adicionais, com capturas antes/depois: o movimento inicial do personagem
foi observado. Durou 115,45 s e terminou pelo limite, sem fatal registrado.
Não foi concluído um combate nem validada a campanha inteira ou a saída de áudio.

Evidências privadas:

- Antes: `017-opening-transition/window-27.png`, cenário escuro.
- Depois: `020-fsi-first-level/input-before-4.png`, cenário/personagem visíveis.
- Movimento: `021-fsi-movement-combat/input-before-4.png` e `input-before-5.png`.

`scripts/play_green_lantern.py` fornece abertura interativa experimental com FSI,
verificação de identidade do build e saves locais. Seu modo `--dry-run` foi
executado; o runtime subjacente foi exercitado pelos probes 019–021. O launcher
Tk não foi anunciado como backend completo nem recebeu um `ready=true` artificial.
