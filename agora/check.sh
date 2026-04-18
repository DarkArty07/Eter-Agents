#!/usr/bin/env bash
# agora/check.sh — verifica que la instalación de Agora es correcta
# Uso: bash ~/.hermes/agora/check.sh

AGORA_PLUGIN=~/.hermes/agora/plugin
PROFILES=(hermes ariadna hefesto)
FAIL=0

echo "=== Agora — verificación de instalación ==="
echo ""

# 1. Verificar symlinks de profiles
echo "── Symlinks de profiles ──"
for profile in "${PROFILES[@]}"; do
    link=~/.hermes/profiles/$profile/plugins/agora
    if [ -L "$link" ]; then
        target=$(readlink -f "$link" 2>/dev/null)
        canonical=$(readlink -f "$AGORA_PLUGIN" 2>/dev/null)
        if [ "$target" = "$canonical" ]; then
            echo "  ✅ $profile → $target"
        else
            echo "  ❌ $profile: symlink apunta a ruta incorrecta"
            echo "       tiene:    $target"
            echo "       esperado: $canonical"
            echo "     Fix: rm -rf $link && ln -s $AGORA_PLUGIN $link"
            FAIL=1
        fi
    elif [ -d "$link" ]; then
        echo "  ❌ $profile: directorio estático (no symlink) — tiene copia desactualizada"
        echo "     Fix: rm -rf $link && ln -s $AGORA_PLUGIN $link"
        FAIL=1
    else
        echo "  ⚠️  $profile: plugin no instalado en $link"
        echo "     Fix: ln -s $AGORA_PLUGIN $link"
        FAIL=1
    fi
done

echo ""

# 2. Verificar que el symlink global también está bien (fallback)
echo "── Symlink global (fallback) ──"
global_link=~/.hermes/plugins/agora
if [ -L "$global_link" ]; then
    target=$(readlink -f "$global_link" 2>/dev/null)
    canonical=$(readlink -f "$AGORA_PLUGIN" 2>/dev/null)
    if [ "$target" = "$canonical" ]; then
        echo "  ✅ plugins/agora → $target"
    else
        echo "  ❌ plugins/agora apunta a ruta incorrecta: $target"
        FAIL=1
    fi
elif [ -d "$global_link" ]; then
    echo "  ❌ plugins/agora: directorio estático (no symlink)"
    echo "     Fix: rm -rf $global_link && ln -s $AGORA_PLUGIN $global_link"
    FAIL=1
else
    echo "  ⚠️  plugins/agora: no instalado (opcional)"
fi

echo ""

# 3. Verificar agent cards
echo "── Agent cards ──"
CARDS_DIR=~/.hermes/agora/plugin/cards
for profile in "${PROFILES[@]}"; do
    card=$CARDS_DIR/$profile.yaml
    if [ -f "$card" ]; then
        available=$(grep "^available:" "$card" | awk '{print $2}')
        if [ "$available" = "true" ]; then
            echo "  ✅ $profile.yaml (available: true)"
        else
            echo "  ⚠️  $profile.yaml (available: $available)"
        fi
    else
        echo "  ❌ $profile.yaml: no existe en $CARDS_DIR"
        FAIL=1
    fi
done

echo ""

# 4. Verificar que tmux está disponible
echo "── Dependencias ──"
if command -v tmux &>/dev/null; then
    echo "  ✅ tmux $(tmux -V 2>/dev/null | awk '{print $2}')"
else
    echo "  ❌ tmux no instalado — Fix: sudo apt install tmux"
    FAIL=1
fi

echo ""

# 5. Resultado final
if [ $FAIL -eq 0 ]; then
    echo "=== ✅ Todo OK — Agora listo para usar ==="
else
    echo "=== ❌ Hay problemas que resolver antes de usar talk_to ==="
fi

exit $FAIL
