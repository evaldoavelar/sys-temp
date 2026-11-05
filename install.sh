#!/usr/bin/env bash
# install.sh - Instalador automatizado do sys-temp / tempmon

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"

echo "==> Instalando dependências Python para sys-temp..."
if command -v pip3 >/dev/null 2>&1; then
    pip3 install --user --break-system-packages -r "${SCRIPT_DIR}/requirements.txt" || pip3 install --user -r "${SCRIPT_DIR}/requirements.txt"
elif command -v pip >/dev/null 2>&1; then
    pip install --user --break-system-packages -r "${SCRIPT_DIR}/requirements.txt" || pip install --user -r "${SCRIPT_DIR}/requirements.txt"
else
    echo "Erro: pip não encontrado. Instale com: sudo apt install python3-pip"
    exit 1
fi

echo "==> Criando diretório de binários do usuário (${BIN_DIR})..."
mkdir -p "${BIN_DIR}"
mkdir -p "${HOME}/bin"

echo "==> Criando links simbólicos em ~/.local/bin e ~/bin..."
chmod +x "${SCRIPT_DIR}/sys-temp"
ln -sf "${SCRIPT_DIR}/sys-temp" "${BIN_DIR}/sys-temp"
ln -sf "${SCRIPT_DIR}/sys-temp" "${BIN_DIR}/tempmon"
ln -sf "${SCRIPT_DIR}/sys-temp" "${HOME}/bin/sys-temp"
ln -sf "${SCRIPT_DIR}/sys-temp" "${HOME}/bin/tempmon"

echo "==> Verificando PATH..."
case ":$PATH:" in
  *":${BIN_DIR}:"*) ;;
  *) echo "AVISO: Adicione export PATH=\"\$HOME/.local/bin:\$PATH\" ao seu ~/.bashrc ou ~/.zshrc" ;;
esac

echo ""
echo "✔ Instalação concluída com sucesso!"
echo "Execute: sys-temp (ou tempmon)"
