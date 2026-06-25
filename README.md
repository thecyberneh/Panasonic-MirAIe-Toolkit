# Panasonic MirAIe Toolkit

> **Control Panasonic Smart ACs from Linux, macOS and Windows — without using the official mobile app for day-to-day control.**

![Python](https://img.shields.io/badge/Python-3.9+-blue)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-success)
![MQTT](https://img.shields.io/badge/Protocol-MQTT-orange)
![Reverse%20Engineered](https://img.shields.io/badge/Reverse-Engineered-red)

Reverse engineered from the Panasonic MirAIe Android application. This toolkit logs into your MirAIe account, discovers devices automatically, and communicates directly with your AC using the same MQTT protocol as the official app.

```
┌──────────────┐       REST API       ┌─────────────────────┐
│  Your Laptop  │◄───────────────────►│  auth.miraie.in     │
│  (Python)     │                     │  app.miraie.in      │
└──────┬───────┘                      └─────────────────────┘
       │
       │  MQTT over TLS (port 8883)
       ▼
┌─────────────────┐     WiFi         ┌──────────────────────┐
│ mqtt.miraie.in  │◄────────────────►│  Panasonic AC        │
│  (MQTT Broker)  │                  │  (ESP32 inside)      │
└─────────────────┘                  └──────────────────────┘
```
---

## Features

- Automatic login using MirAIe credentials
- Automatic device discovery
- MQTT over TLS
- Power ON/OFF
- Temperature control
- Mode control (Cool, Heat, Dry, Fan, Auto)
- Fan speed control
- Swing control
- Eco & Turbo modes
- Firmware download
- Live status monitoring
- Beautiful CLI output
- Optional `--debug` mode with raw MQTT/API traffic

---

## Quick Start

```bash
git clone https://github.com/thecyberneh/Panasonic-MirAIe-Toolkit.git
cd Panasonic-MirAIe-Toolkit

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

echo "9876543210 your_password" > credentials.txt

python3 miraie_ac_control.py discover

python3 miraie_ac_control.py on
```

---

## Example

```text
$ python3 miraie_ac_control.py on

[*] Turning AC on...
[+] AC is on.

$ python3 miraie_ac_control.py temp 24

[*] Setting temperature to 24°C...
[+] Temperature is set to 24°C.
```

Use `--debug` to display raw MQTT packets:

```bash
python3 miraie_ac_control.py --debug status
```

---

## Commands

| Command | Description | Example |
|---------|-------------|---------|
| discover | Login, fetch home/device details | `python3 miraie_ac_control.py discover` |
| on | Turn AC ON | `python3 miraie_ac_control.py on` |
| off | Turn AC OFF | `python3 miraie_ac_control.py off` |
| temp <16-30> | Set target temperature (°C) | `python3 miraie_ac_control.py temp 24` |
| mode <auto\|cool\|heat\|fan\|dry> | Set operating mode | `python3 miraie_ac_control.py mode cool` |
| fan <auto\|high\|medium\|low\|quiet> | Set fan speed | `python3 miraie_ac_control.py fan auto` |
| swing <auto\|on\|off> | Swing on/off/auto | `python3 miraie_ac_control.py swing auto` |
| vswing <0-7> | Vertical swing position | `python3 miraie_ac_control.py vswing 3` |
| hswing <0-7> | Horizontal swing position | `python3 miraie_ac_control.py hswing 5` |
| turbo | Enable turbo mode | `python3 miraie_ac_control.py turbo` |
| unturbo | Disable turbo mode | `python3 miraie_ac_control.py unturbo` |
| powerful | Enable powerful mode | `python3 miraie_ac_control.py powerful` |
| eco | Enable eco mode | `python3 miraie_ac_control.py eco` |
| uneco | Disable eco mode | `python3 miraie_ac_control.py uneco` |
| buzzer <on\|off> | Control remote beep | `python3 miraie_ac_control.py buzzer off` |
| refresh | Request full state from AC | `python3 miraie_ac_control.py refresh` |
| status | Live MQTT status feed (Ctrl+C to stop) | `python3 miraie_ac_control.py status` |

---

## Architecture

```text
        MirAIe Cloud
      (REST + MQTT/TLS)
             ▲
             │
      Authentication
             │
      Device Discovery
             │
      MQTT Commands
             │
      Panasonic Smart AC
```

---

## Repository Structure

```text
Panasonic-MirAIe-Toolkit/
├── miraie_ac_control.py
├── requirements.txt
├── credentials.txt.example
├── README.md
└── docs/
```

## Onboarding (New AC Pairing)

> **⚠️ Note:** I've written BLE and WiFi-AP onboarding scripts (`ble_onboard.py` and `onboarding.py`) that handle the full onboarding flow — BLE scanning, GATT connection, AES-256-CBC + RSA encryption, and WiFi credential transfer. The first two stages work correctly: the AC receives and decrypts the payload (code 101), and connects to WiFi (code 110). However, the final **cloud registration** step fails with:
> ```
> code 117: register_device_with_cloud:675
> ```
> The AC's `deviceRegistrationToken` is one-time-use and the MirAIe cloud requires a **Matter CHIP SDK** commissioning flow (`chip.devicecontroller`) to complete registration — a C++ library integrated into the Android app that I haven't been able to replicate in Python yet.
>
> **If you have experience with the Matter SDK and can fix this, please open a PR!** The BLE protocol is fully reverse-engineered and documented below.
>
> **Workaround:** Use the MirAIe Android app for the initial pairing (2 minutes), then control the AC from Linux forever with this toolkit.

### How Onboarding Works

The AC runs an ESP32-C3 (2023+ models) or ESP8266 (2021-2022 models). During onboarding, your phone sends WiFi credentials to the AC so it can connect to your home network and register with the MirAIe cloud.

#### Method A: BLE (2023+ ESP32-C3 Models)

Your AC uses Bluetooth LE for onboarding. It does **not** create a WiFi hotspot.

1. Press and hold the **Smart** button on the remote for 5-6 seconds until the WiFi LED blinks
2. The AC broadcasts as a BLE device named **"PANA_AC"** with manufacturer ID `0x003A`
3. The app scans BLE, finds the AC, and connects via GATT
4. Service UUID: `UUID`
5. Characteristic UUID: `UUID`
6. The AC sends a greeting: `"Hello from Mirai"`
7. The app sends a handshake: `{"type":"ob","size":<payload_bytes>}`
8. The AC responds with code 113 (payload length OK)
9. The app encrypts WiFi credentials with AES-256-CBC (random key) + RSA (AC's public key)
10. The app sends the encrypted payload in 180-byte BLE chunks
11. The AC responds with status codes: 101 (decrypt success) → 110 (WiFi connected) → 200 (registered)
12. After each intermediate code, the app sends `{"type":"continue","size":-1}` to progress
13. On success (code 200), the app sends `{"type":"exit","size":-2}` and disconnects

**Onboarding payload format:**
```json
{
  "BSSID": "",
  "deviceName": "Bedroom AC",
  "homeId": "<home_id>",
  "endPoint": "https://app.miraie.in",
  "useProd": "1",
  "spaceId": "<space_id>",
  "userId": "<user_id>",
  "wifipassword": "<wifi_password>",
  "wifissid": "<wifi_ssid>"
}
```

**Encryption:** AES-256-CBC with random key + random IV. The key and IV are encrypted with the AC's RSA public key (PKCS1v15). The final envelope:
```json
{
  "deviceRegistrationToken": "<token_from_cloud>",
  "iv": "<RSA_encrypted_iv_hex>",
  "key": "<RSA_encrypted_key_hex>",
  "payload": "<AES_encrypted_onboarding_json_hex>",
  "version": "1.0"
}
```

**Status codes (from `OnBoardingService.java`):**
| Code | Meaning |
|------|---------|
| 113 | Payload length OK |
| 101 | Payload decrypted successfully |
| 110 | WiFi connection progressing |
| 111 | Connected to cloud |
| 112 | Registration in progress |
| 200 | Complete success |
| 116 | Device already registered (AONB) |
| 117 | Cloud registration error |

#### Method B: WiFi AP (2021-2022 ESP8266 Models)

Older models create a temporary WiFi hotspot:

1. Press the WiFi button on the remote for 5 seconds
2. Connect your laptop to the AC's WiFi network: **"Panasonic_AC_XXXX"**
3. The AC runs a TCP server at `192.168.4.1:443`
4. Send a handshake: `{"type":"ob","size":<payload_bytes>}`
5. Send the encrypted onboarding payload
6. AC connects to your WiFi and registers

#### Getting Device Keys for Onboarding

The app obtains the AC's public key and registration token via cloud API:

```
1. Scan QR code on AC unit → get Matter onboarding payload
2. GET certificateManager/qrcode?qrcode=<payload>
   Header: X-Tenant-ID: panasonic
   → returns productSerialNumber, modelId, vendorId, etc.
3. GET deviceManagement/devices/productSerialNumber/<PSN>
   → returns devicePublicKey, deviceRegistrationTokenEncrypted
```

The QR code (`MT:OOG02KCT14Q...`) is a Matter manual pairing code. The API endpoint requires `X-Tenant-ID` header set to `panasonic` (lowercase). Alternatively, the PSN is broadcast in the BLE advertisement's manufacturer data.

---

## How It Works

### Architecture

```
Login:  POST auth.miraie.in/simplifi/v1/userManagement/login
        Body: {clientId, mobile, password, scope}
        → accessToken + userId

Discover: GET app.miraie.in/simplifi/v1/homeManagement/homes
        → homeId, spaceId, deviceId

Control: MQTT publish to mqtt.miraie.in:8883 (TLS 1.2)
        Topic: {userId}/{homeId}/{deviceId}/control
        Auth: username=homeId, password=accessToken
```

### MQTT Topics

| Topic Suffix | Purpose |
|-------------|---------|
| `control` | Send commands to AC |
| `status` | Device state (power, mode, temp, fan, etc.) |
| `connectionStatus` | Online/offline |
| `rstate` | Remote state / errors |
| `diag` | Diagnostic telemetry |

### Command Format

```json
{"ps": "on", "ki": 0, "cnt": "an", "sid": "1"}
```

| Field | Purpose |
|-------|---------|
| `ki` | Key index (capability-specific) |
| `cnt` | Controller: `"an"`=Android, `"gw"`=Gateway |
| `sid` | Sequence ID (monotonically increasing) |

---

---

## Reverse Engineering

This project is based on reverse engineering of:

- MirAIe Android App
- Authentication APIs
- MQTT protocol
- Device discovery APIs
- Firmware update APIs
- BLE onboarding research

Detailed protocol notes should live in the `docs/` directory.

---

## Roadmap

- [x] Device discovery
- [x] MQTT control
- [ ] Firmware download
- [x] Live status

---

## Disclaimer

This project is provided for educational, interoperability, and research purposes only.

It is not affiliated with or endorsed by Panasonic.

---

## Contributing

Issues, feature requests and pull requests are welcome.

If this project helps you, consider giving it a ⭐ on GitHub.
