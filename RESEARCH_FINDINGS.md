# Panasonic MirAIe AC - Reverse Engineering Findings (v01.4.25)

## Summary

Decompiled `com.panasonic.in.miraie` version **01.4.25** (version_code=231301425) from XAPK
using JADX 1.5.5. Key findings compared against the original research (2021 APK version).

## API Endpoints

All endpoints under the `/simplifi/v1/` base path. Identity under `/api/identity/v1/`.

| Service      | URL                                    | Purpose              |
|-------------|----------------------------------------|----------------------|
| API Base     | `https://app.miraie.in/simplifi/v1/`   | Main API             |
| Auth Base    | `https://auth.miraie.in/simplifi/v1/`  | Authentication       |
| IAM Identity | `https://iam.miraie.in/api/identity/v1/` | OAuth2 token exchange |
| MQTT Broker  | `ssl://mqtt.miraie.in:8883`           | Device control       |
| Anchor       | `https://vetaar-anchor.com/VCAPI3/`   | External integration |
| eWarranty    | `https://ecarewiz.com/`               | Warranty             |

### Pre-Production Endpoints (from `PreProdEndpointModule.java`)

| Service      | URL                                              |
|-------------|--------------------------------------------------|
| API         | `https://api-preprod.lifestyleindia.net/simplifi/v1/` |
| Auth        | `https://auth-preprod.lifestyleindia.net/simplifi/v1/` |
| MQTT        | `ssl://mqtt-preprod.lifestyleindia.net:8883`         |

## Client IDs / Secrets

| Name                  | Value                                                    | Usage          |
|-----------------------|----------------------------------------------------------|----------------|
| IAM_CLIENT_ID         | `292d99d7-5623-4157-8a71-846ee3ff5dbf`                  | User login     |
| IAM_TV_CLIENT_ID      | `ClQTZNaZmJNdQzrzz8AEQ95yDmUa`                          | TV device login|
| PGO_WEB_AUTH_CLIENT_ID| `b5e09ec1-a0ea-44b1-b15b-4408f521183d`                  | Web auth       |
| ANCHOR_CLIENT_ID      | `plsil.application-oa2-client.5d98df57d67047dc8e511e6045dg4h5a` | Anchor (vetaar) |
| PreProd IAM_CLIENT_ID | `KS0RQd42s9AaBTU6cKv_MmrKuWMa`                          | Pre-prod env   |
| PreProd ANCHOR_ID     | `plsil.application-oa2-client.2c84ab15d67047dc8e511a0645df3fca` | Pre-prod anchor|

### Key Change from Original Research
- **Old clientId**: `PBcMcfG19njNCL8AOgvRzIC8AjQa` (simple alphanumeric)
- **New clientId**: `292d99d7-5623-4157-8a71-846ee3ff5dbf` (UUID format, IAM-based)
- Login now requires a `scope` field: format `"an_" + random_9_digits`

## Authentication Flow

### 1. User Login
```
POST https://auth.miraie.in/simplifi/v1/userManagement/login
Body: {
    "clientId": "292d99d7-5623-4157-8a71-846ee3ff5dbf",
    "mobile": "+91XXXXXXXXXX",      // or "email" for email login
    "password": "user_password",
    "scope": "an_XXXXXXXXX"          // Generated: "an_" + random(0..999999999)
}
Response: {
    "accessToken": "...",
    "refreshToken": "...",
    "expiresIn": 3600,
    "userId": "..."
}
```

### 2. Device Login (for TV/STB devices)
```
POST https://auth.miraie.in/simplifi/v1/userManagement/login
Body: {
    "clientId": "ClQTZNaZmJNdQzrzz8AEQ95yDmUa",
    "userName": "...",
    "password": "..."
}
```

### 3. Token Refresh
```
POST https://auth.miraie.in/simplifi/v1/userManagement/tokenRefresh
Body: {
    "token": "<refresh_token>",
    "clientId": "292d99d7-5623-4157-8a71-846ee3ff5dbf"
}
```

### 4. OTP Flow
```
Generate: POST otpManagement/otpGeneration
Verify:   POST otpManagement/otpValidation
```

## Key API Endpoints

### Home Management
```
GET    homeManagement/homes                              # List homes
POST   homeManagement/homes                              # Create home
POST   homeManagement/homes/{homeId}/spaces              # Create space
DELETE homeManagement/homes/{homeId}/spaces/{spaceId}    # Delete space
```

### Device Management
```
GET    deviceManagement/devices/macAddress/{mac}          # Lookup device by MAC
GET    deviceManagement/devices/deviceId/{deviceId}       # Lookup device by ID
GET    deviceManagement/devices/deviceSerialNumber/{sn}   # Lookup by serial number
GET    deviceManagement/devices/efuseMacAddress/{mac}     # Lookup by eFuse MAC
POST   deviceManagement/deviceRegistration/tv            # Register TV device
POST   deviceManagement/devices/{deviceId}/deviceOffboard # Remove device
PUT    homeManagement/homes/{homeId}/spaces/{spaceId}/devices/{deviceId}  # Update name
```

### FOTA (Firmware Over-The-Air)
```
GET    fota/firmware/deviceId/{deviceId}/download?currentVersion={ver}
GET    fota/firmware/model/{modelId}/download?currentVersion={ver}
```
Response: `{"url": "...", "firmwareVersion": "...", "signatureUrl": "...", "cd": "...", "modelNumber": "...", "isLatestVersion": true/false, "message": "..."}`

### Weather
```
GET    services/weather/current?lat={lat}&lon={lon}
```

### Sleep Profiles
```
POST   homeManagement/homes/{h}/spaces/{s}/devices/{d}/sleepProfile
GET    homeManagement/homes/{h}/spaces/{s}/devices/{d}/sleepProfile
PUT    homeManagement/homes/{h}/spaces/{s}/devices/{d}/sleepProfile/{p}
DELETE homeManagement/homes/{h}/spaces/{s}/devices/{d}/sleepProfile/{p}
```

## MQTT Protocol

### Connection
- Broker: `mqtt.miraie.in:8883` (TLS 1.2)
- Username: `homeId` (or `homeId@appBrand` for branded clients)
- Password: `accessToken`
- Client ID: `{SOURCE}{hash(userId##homeId)[:16]}{install_time[-5:]}`

### Topic Structure
```
{userId}/{homeId}/{deviceId}/control    # Send commands to device
{userId}/{homeId}/{deviceId}/tcontrol   # Control for Comfort Cloud / Intesis AC
{userId}/{homeId}/{deviceId}/status     # Device status updates
{userId}/{homeId}/{deviceId}/fcontrol   # Firmware control
{userId}/{homeId}/{deviceId}/fstatus    # Firmware status
{userId}/{homeId}/{deviceId}/onbs       # Onboarding state
{userId}/{homeId}/{deviceId}/pstatus    # Detailed status
{userId}/{homeId}/{deviceId}/rstate     # Remote state (IR devices)
{userId}/{homeId}/{deviceId}/aicontrol  # AI control
{userId}/{homeId}/{deviceId}/aistatus   # AI status
{userId}/{homeId}/{deviceId}/pwC        # Power consumption
```

### Control Message Format
All messages are JSON with these common fields:
- `ki` (key index): capability-specific index
- `cnt` (controller): "an" (Android), "gw" (Gateway), "TV" (TV)
- `sid` (sequence ID): incrementing counter

### AC Control Commands (from `BaseCapability.Type` enum)

| Command    | JSON Key  | Values                                  |
|-----------|-----------|-----------------------------------------|
| Power     | `ps`      | `"on"`, `"off"`                         |
| Mode      | `acmd`    | `"auto"`, `"cool"`, `"heat"`, `"fan"`, `"dry"` |
| Temp      | `actmp`   | `"16.0"` - `"30.0"` (as string)         |
| Fan Speed | `acfs`    | `"auto"`, `"high"`, `"medium"`, `"low"`, `"quiet"` |
| Swing     | `swing`   | `"auto"`, `"on"`, `"off"`               |
| V-Swing   | `acvs`    | `"0"` - `"7"`                           |
| H-Swing   | `achs`    | `"0"` - `"7"`                           |
| Turbo     | `turbo`   | `"on"`, `"off"`                         |
| Powerful  | `pwmd`    | `"on"`, `"off"`                         |
| Eco       | `eco`     | `"on"`, `"off"`                         |
| Buzzer    | `bzctrl`  | `"on"`, `"off"`                         |
| Humidifier| `hmdfr`   | `"on"`, `"off"`                         |
| NanoeX    | `nanoex`  | `"on"`, `"off"`                         |
| Ionizer   | `ionizer` | `"on"`, `"off"`                         |
| Gen Mode  | `genmd`   | Varies by model                         |
| Convertible| `convmd` | Varies by model                         |
| Timer     | `timer`   | Timestamp                               |
| Display   | `dctl`    | `"on"`, `"off"`                         |

### Example: Turn AC on + set cool mode + 24°C + auto fan
```json
{"ps":"on","ki":0,"cnt":"an","sid":"1"}
{"acmd":"cool","ki":0,"cnt":"an","sid":"2"}
{"actmp":"24.0","ki":0,"cnt":"an","sid":"3"}
{"acfs":"auto","ki":0,"cnt":"an","sid":"4"}
```

### Status Message Parsing
Status messages come in on the `status` topic. Key fields:
- `ps`: power state
- `acmd`: current mode
- `actmp`: current set temperature
- `acfs`: current fan speed
- `roomtemp`: room temperature (from sensor)
- `errors`: comma-separated error codes (AC faults)
- `totalOperatingHours`: total run time
- `filterDustLevel`: filter dust percentage
- `filterCleaningRequired`: boolean
- `onlineStatus`: device connectivity

## Onboarding Protocol

1. Connect to AC's WiFi AP (192.168.4.1, no password typically)
2. Open TCP connection to `192.168.4.1:443`
3. Send: `{"type": "ob", "size": <payload_size>}`
4. Receive ACK
5. Send encrypted payload (see `onboarding-2.py` in original research)
6. Receive response with status code

### Error Codes
- 200/201: Success
- 116 (0x74): `D2M_MSG_REGISTRATION_DEVICE_ALREADY_ADDED` - AONB error

### Crypto (unchanged from original)
- AES-256-CBC with all-zero key + IV
- Key + IV encrypted with device's RSA public key (PKCS1v15 padding)
- PKCS7 padding for AES payload
- Hex-encoded ciphertext

## Device Details Response

```json
{
  "deviceId": "...",
  "macAddress": "AA:BB:CC:DD:EE:FF",
  "modelNumber": "...",
  "modelName": "...",
  "brand": "PANASONIC",
  "category": "AC",
  "firmwareVersion": "X.X.X",
  "fwVersion": "X.X.X",
  "chipType": "...",
  "deviceRegistrationTokenEncrypted": "...",
  "devicePublicKey": "-----BEGIN PUBLIC KEY-----...",
  "isMatterEnabled": false,
  "serialNumber": "...",
  "productSerialNumber": "...",
  "qrCode": "...",
  "vendorId": ...,
  "productId": ...,
  "nodeId": "...",
  "manualCode": "...",
  "dacHash": "...",
  "customFields": "..."
}
```

## ESP8266 Firmware Notes

From the original research, the AC controller uses ESP8266 with ESP8266_RTOS_SDK.
Firmware can be extracted via:
1. FOTA endpoint (see above)
2. Analyzing with: `esptool.py --chip auto image_info ac_firmware.bin`
3. Reverse engineering with Ghidra + ghidra-xtensa plugin

## Matter / Thread Support

New in this version: Matter protocol support via CHIP SDK (`chip.devicecontroller`).
Devices with `isMatterEnabled: true` support Matter commissioning.
Endpoints:
```
POST admservices/fabric/controller           # Get controller NOC
POST admservices/fabric/node                 # Get device NOC
POST deviceManagement/devices/matterdevice   # Onboard Matter device
```

## Pre-Production Environment

Set `PROD_ENV = false` in BuildConfig to use pre-prod endpoints.
Pre-prod endpoints are on `lifestyleindia.net` domain instead of `miraie.in`.

## References
- ESP8266 RTOS SDK: https://github.com/espressif/ESP8266_RTOS_SDK
- Ghidra Xtensa plugin: https://github.com/Ebiroll/ghidra-xtensa
- Matter/CHIP: https://buildwithmatter.com
- CSA-IoT DCL: https://on.dcl.csa-iot.org/dcl/pki/certificates
