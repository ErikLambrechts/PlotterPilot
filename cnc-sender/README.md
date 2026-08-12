# Plotbot CNC Sender

Minimal web-based controller for a FluidNC machine.

## Requirements

- Python 3
- FluidNC CNC controller reachable over TCP
- mDNS/hostname resolution for `plotbot.local`, or an IP address

## Configuration

Edit `config.yaml`.

The default configuration uses:

    host: plotbot.local
    port: 23

## Run

    ./run.sh

Then open:

    http://127.0.0.1:5000

## Controls

### Mouse

Click anywhere in the machine workspace to move the head there.

### Keyboard

- Arrow keys: X/Y jogging
- PageUp: Z+
- PageDown: Z-
- Shift: multiply jog distance by 10

### Buttons

- X+/X-
- Y+/Y-
- Z+/Z-
- Home X
- Home Y
- Home XY
- Connect
- Disconnect

## Real controller position

The sender now requests FluidNC realtime status using `?`.

FluidNC status reports contain the actual machine position, for example:

    <Idle|MPos:10.000,20.000,0.000|FS:3000,0>

The displayed X/Y/Z position therefore comes from the controller rather than
being estimated locally.

The application requests status approximately once per second.
