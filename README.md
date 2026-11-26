<div align="center">

# 🖥️ BSPWM Installer Pro

![Status](https://img.shields.io/badge/status-en%20desarrollo-yellow)
![Platform](https://img.shields.io/badge/platform-VMware-blue)

Script automatizado para configurar un entorno completo basado en **bspwm** en sistemas Debian/Ubuntu y derivados como Parrot OS.

</div>

<p align="center">
  <img src="img/image.png" width="800" alt="Vista previa del entorno BSPWM"/>
</p>

## 📑 Tabla de contenido

- [Características](#-características)
- [Capturas](#-capturas)
- [Requisitos](#-requisitos)
- [Instalación](#-instalación)
- [Créditos](#-créditos)
- [Licencia](#-licencia)

## ✨ Características

- Instalación automática de dependencias.
- Compilación de herramientas esenciales.
- Configuración del entorno de escritorio:
  - Zsh
  - Polybar
  - Picom
  - y más
- Copia automática de dotfiles.
- Personalización completa del sistema.

## ⚙️ Requisitos

- Sistema basado en Debian/Ubuntu.
- Usuario con permisos `sudo`.
- Conexión a internet.

> ⚠️ **No ejecutar como root.**

## 🚀 Instalación

```bash
git clone https://github.com/AmasterJT/linux-personalization.git
cd linux-personalization
bash install-bspwm.sh
```

El instalador compila el selector de ventanas y el control de audio en C.
El selector usa GTK 3 y X11. El panel de audio y su indicador usan la interfaz
PulseAudio de PipeWire. Los binarios se generan en los directorios de scripts
de BSPWM y Polybar.

Para recompilar solo esos dos componentes en una instalación existente,
con las dependencias de compilación ya instaladas, ejecuta:

```bash
sh Config/bspwm/window-switcher/build.sh
sh Config/polybar/audio-control/build.sh
```

Si el control de audio ya estaba en ejecución, termina esa instancia con
`~/.config/polybar/scripts/audio-control quit`. El siguiente clic en el icono
de volumen o la siguiente pulsación de una tecla de volumen iniciará la nueva.

## 🙌 Créditos

Desarrollado por **AmasterJT**.

Inspirado en la necesidad de automatizar y simplificar la configuración de un entorno **bspwm** funcional, limpio y personalizado.
