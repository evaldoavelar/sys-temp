# sys-temp 🌡️💻

> **Monitor visual de hardware, temperaturas e recursos para terminais Linux**, inspirado no design moderno do [Sampler](https://sampler.dev) e na praticidade do [htop](https://htop.dev).

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform Linux](https://img.shields.io/badge/Platform-Linux-orange.svg)](https://kernel.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 📸 Visão Geral

```text
                       FRIO                                                 QUENTE                       
                       ████ ████ ████ ████ ████ ████ ████ ████ ████ ████ ████ ████                       
                                                  ▲                                                      
                                               48.0°C                                                    
                       0°C                                                   100°C                       

 Dell Inspiron (cst-tux) | Core i7-8550U (4C/8T)               Uptime: 3h 4m        Load: 0.44 0.56 0.60 

╭─  CPU Usage History  ────────────────────────────╮  ╭─  Thermal Timeline (°C)  ───────────────────────╮
│                                           100%   │  │ 48°C ┼───────────────                           │
│                                                  │  │ 48°C ┤                                          │
│                                            50%   │  │ 48°C ┤                                          │
│                                                  │  │ 47°C ┤                                          │
│ ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄   0%   │  │ 47°C ┤───────────────                           │
│ Atual: 12.3%   Média: 12.3%   Pico: 12.3%        │  │ ● CPU Pkg: 48°C   ● GPU MX150: 47°C             │
╰──────────────────────────────────────────────────╯  ╰─────────────────────────────────────────────────╯

╭─  Hardware Gauges & Levels  ─────────────────────╮  ╭─  Sensors & Top CPU Processes  ─────────────────╮
│ Cooler Fan    2604 RPM  (45%)  [BAIXO]           │  │ Sensores:  NVMe 38°   PCH 46°   RAM 44°         │
│ [||||||||||||||||||||                         ]  │  │ Núcleos:   C0:48° C1:46° C2:47° C3:49° (2.4G)   │
│ Memória RAM   5.6/15.5 GiB  (42%)  Disp: 9.0G    │  │ Gráficos:  UHD: 300MHz • MX150: 47° • Amb: 42°  │
│ [|||||||||||||||||||                          ]  │  │ ─────────────────────────────────────────────── │
│ Swap Cache    1/4096 MiB  (0%)  Livre: 4.0G      │  │ PID    PROCESSO           CPU%    MEM%          │
│ [                                             ]  │  │  76080  python3          22.7%    0.1%          │
│ Disco SSD (/) 422/499 GiB  (85%)  Livre: 77G     │  │   1924  dockerd           8.5%    0.6%          │
│ [||||||||||||||||||||||||||||||||||||||       ]  │  │  15810  java              5.7%    1.9%          │
╰──────────────────────────────────────────────────╯  ╰─────────────────────────────────────────────────╯

Comandos: [q] Sair  [Espaço] Pausar  [1] 1s  [2] 2s  [c] Layout  | 12:12:08
```

---

<img width="540" height="1168" alt="image" src="https://github.com/user-attachments/assets/3cffab27-bc35-4bb5-a26d-d2a5c1b77c93" />


## ✨ Recursos

- **🌡️ Termômetro Mestre (Master Gauge)**:
  - 12 blocos coloridos em escala RGB calibrada (Azul `(30,70,230)` até Vermelho Escuro `(200,25,45)`).
  - Ponteiro dinâmico `▲` centralizado sobre o bloco ativo.
  - Alinhamento de cabeçalho: `FRIO` à esquerda e `QUENTE` à direita, sem poluição visual.
- **📊 Medidores de Nível estilo `htop`**:
  - Exibição de texto na linha superior e barra de progresso com pipes `[|||||||   ]` na linha de baixo.
  - Gradiente térmico progressivo em cada pipe: frio (azul/ciano/verde) evoluindo para quente (amarelo/laranja/vermelho).
  - Medição de Ventoinhas (RPM e faixa de carga), Memória RAM, Swap Cache e Disco SSD (`/`).
- **🎯 Sensores & Top Processos CPU/RAM**:
  - Sensores térmicos por componente: **NVMe SSD**, Chipset **PCH**, **RAM SODIMM** e **Ambiente**.
  - Monitoramento individual por núcleo de CPU (`C0`, `C1`, `C2`, `C3`) com indicação de clock médio em tempo real.
  - Monitoramento de gráficos híbridos: **Intel UHD 620** (com aceleração Intel QSV) e **NVIDIA GeForce MX150**.
  - Tabela formatada dos maiores consumidores de processamento com `PID`, `PROCESSO`, `CPU%` e `MEM%`.
- **📈 Gráficos Históricos 2D Integrados**:
  - Histograma vertical de uso de CPU estilo Sampler (com blocos ` ▂▃▄▅▆▇█` e métricas Atual/Média/Pico).
  - Gráfico de linha temporal térmica multi-série em tempo real (CPU Pkg vs GPU dedicada).
- **📐 Layout Responsivo & Anti-Scroll**:
  - Ajusta-se perfeitamente de 80 a 140+ colunas.
  - Detecção automática de altura do terminal para nunca estourar a tela ou gerar scroll indesejado.
  - Alternância entre colunas paralelas ou pilha compacta.

---

## 🚀 Instalação Rápida

### Opção 1: Via Script Automatizado (Recomendado)

```bash
git clone https://github.com/evaldoavelar/sys-temp.git
cd sys-temp
./install.sh
```

O script instala as bibliotecas Python necessárias e cria os atalhos `sys-temp` e `tempmon` em `~/.local/bin` e `~/bin`.

### Opção 2: Instalação Manual

1. Instale as dependências:
   ```bash
   pip install --user -r requirements.txt
   ```
2. Torne o script executável e crie o atalho:
   ```bash
   chmod +x sys-temp
   ln -sf "$(pwd)/sys-temp" ~/.local/bin/sys-temp
   ln -sf "$(pwd)/sys-temp" ~/.local/bin/tempmon
   ```

---

## 🎮 Como Usar

### Execução Contínua em Tempo Real

```bash
sys-temp
# ou
tempmon
```

### Captura Única (Snapshot)

Ideal para scripts, diagnósticos rápidos ou integração com outros utilitários:

```bash
sys-temp --once
```

### Ajuste de Intervalo e Layout

```bash
# Atualização a cada 2 segundos:
sys-temp -i 2.0

# Forçar layout vertical compacto:
sys-temp -c
```

---

## ⌨️ Atalhos Interativos

| Tecla | Ação |
| :---: | :--- |
| <kbd>q</kbd> | Encerra o monitor e limpa o terminal |
| <kbd>Espaço</kbd> | Pausa / Retoma a atualização em tempo real |
| <kbd>1</kbd> | Ajusta taxa de atualização para **1 segundo** |
| <kbd>2</kbd> | Ajusta taxa de atualização para **2 segundos** |
| <kbd>c</kbd> | Alterna entre layout em colunas e layout compacto |

---

## 🛠️ Requisitos e Compatibilidade

- **Sistema Operacional**: Linux (testado em Ubuntu 24.04 LTS / Debian / Arch / Fedora).
- **Python**: 3.10 ou superior.
- **Hardware Suportado**:
  - **Processadores**: Intel Core (qualquer geração moderna com `coretemp`/`thermal_zone`) e AMD Ryzen (`k10temp`).
  - **Refrigeração**: Módulos de ventoinha `dell_smm` (laptops Dell Inspiron, XPS, Latitude, Vostro) e genéricos via `psutil.sensors_fans`.
  - **Placas Gráficas**:
    - GPUs NVIDIA dedicadas (leitura via driver proprietário `nvidia-smi`).
    - GPUs Intel integradas (UHD / Iris / Arc via `/sys/class/drm/card*`).
  - **Armazenamento**: NVMe (`nvme` subsystem) e sensores de placa `pch_skylake` / `acpitz`.

---

## 📄 Licença

Distribuído sob a licença **MIT**. Consulte o arquivo [LICENSE](LICENSE) para obter mais informações.
