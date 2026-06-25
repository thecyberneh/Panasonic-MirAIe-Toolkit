#!/usr/bin/env python3
"""
BLE-based Onboarding for Panasonic AC (2023+ ESP32-C3 models)

Usage:
  python3 ble_onboard.py --ssid "YourWiFi" --password "YourPassword"
"""

import asyncio, json, sys, argparse, secrets, binascii
from bleak import BleakClient
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, padding as sym_padding
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# BLE identifiers from decompiled MirAIe app
ONB_SERVICE_UUID = 'b2bbc642-46da-11ed-b878-0242ac120002'
ONB_CHAR_UUID = 'c9af9c76-46de-11ed-b878-0242ac120002'
MTU = 200
CHUNK_SIZE = 180  # MTU - 20 bytes overhead

def load_device_data():
    with open('ac_details.txt') as f:
        ac = json.load(f)[0]
    with open('device_public_key.txt', 'rb') as f:
        pubkey_pem = f.read()
    with open('login_data.txt') as f:
        login = json.load(f)
    with open('home_plus_user_details.txt') as f:
        home = json.load(f)[0]
    return {
        'device_reg_token': ac['deviceRegistrationTokenEncrypted'],
        'public_key_pem': pubkey_pem,
        'home_id': home['homeId'],
        'space_id': home['spaces'][0]['spaceId'],
        'user_id': login['userId'],
    }

def encrypt_payload(onboarding_json: str, public_key_pem: bytes, device_reg_token: str) -> bytes:
    """Encrypt onboarding payload with AES-256-CBC + RSA (same as app)."""
    # Generate random AES-256 key and IV
    aes_key = secrets.token_bytes(32)
    iv = secrets.token_bytes(16)

    # Encrypt onboarding JSON with AES-256-CBC
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(onboarding_json.encode()) + padder.finalize()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    # Encrypt AES key and IV with device RSA public key
    pubkey = serialization.load_pem_public_key(public_key_pem)
    enc_key = pubkey.encrypt(aes_key, asym_padding.PKCS1v15())
    enc_iv = pubkey.encrypt(iv, asym_padding.PKCS1v15())

    # Build EncryptedPayload
    payload = {
        'deviceRegistrationToken': device_reg_token,
        'iv': binascii.hexlify(enc_iv).decode(),
        'key': binascii.hexlify(enc_key).decode(),
        'payload': binascii.hexlify(ciphertext).decode(),
        'version': '1.0'
    }
    return json.dumps(payload).encode()

async def scan_for_ac():
    """Scan BLE for PANA_AC device."""
    from bleak import BleakScanner
    print('[*] Scanning BLE for Panasonic AC...')
    ac_addr = None
    def callback(device, adv_data):
        nonlocal ac_addr
        if adv_data.manufacturer_data and 0x003A in adv_data.manufacturer_data:
            data = adv_data.manufacturer_data[0x003A]
            serial = data.decode('ascii', errors='ignore')
            print(f'[+] Found: {device.name} ({device.address}) RSSI:{adv_data.rssi}dBm Serial:{serial}')
            ac_addr = device.address
    async with BleakScanner(callback) as scanner:
        for _ in range(15):
            if ac_addr:
                return ac_addr
            await asyncio.sleep(1)
    return None

async def onboard(ssid: str, password: str):
    # Find AC
    ac_addr = await scan_for_ac()
    if not ac_addr:
        print('[!] AC not found. Make sure it is in pairing mode (WiFi LED blinking).')
        return False
    print(f'[*] Using device: {ac_addr}')

    # Load cloud data
    data = load_device_data()
    print(f"[*] Home: {data['home_id']}, Space: {data['space_id']}")

    # Build onboarding JSON (format from OnboardingPayload.java)
    onboarding_json = json.dumps({
        'BSSID': '',
        'deviceName': 'Bedroom AC',
        'homeId': data['home_id'],
        'endPoint': 'https://app.miraie.in',
        'useProd': '1',
        'spaceId': data['space_id'],
        'userId': data['user_id'],
        'wifipassword': password,
        'wifissid': ssid
    })
    print(f'[*] Onboarding payload: {len(onboarding_json)} bytes')

    # Encrypt
    encrypted = encrypt_payload(onboarding_json, data['public_key_pem'], data['device_reg_token'])
    print(f'[*] Encrypted payload: {len(encrypted)} bytes')
    print(f'    Encrypted data: {encrypted[:100]}...')

    # Connect to AC via BLE
    print(f'[*] Connecting to {ac_addr}...')
    async with BleakClient(ac_addr, timeout=20.0) as client:
        print('[+] BLE connected!')

        # Read current value (should say "Hello from Mirai")
        val = await client.read_gatt_char(ONB_CHAR_UUID)
        print(f"[*] AC greeting: {val.decode(errors='ignore')}")

        # Send handshake: {"type":"ob","size":<payload_size>}
        handshake = json.dumps({'type': 'ob', 'size': len(encrypted)}).encode()
        print(f'[*] Sending handshake: {handshake}')
        await client.write_gatt_char(ONB_CHAR_UUID, handshake)

        # Wait for ACK
        await asyncio.sleep(1.0)

        # Send encrypted payload in chunks (same as app: split by CHUNK_SIZE)
        payload_str = encrypted.decode()
        chunks = [payload_str[i:i+CHUNK_SIZE] for i in range(0, len(payload_str), CHUNK_SIZE)]
        print(f'[*] Sending {len(chunks)} chunk(s) of {CHUNK_SIZE} bytes each...')
        for i, chunk in enumerate(chunks):
            await client.write_gatt_char(ONB_CHAR_UUID, chunk.encode())
            print(f'    Chunk {i+1}/{len(chunks)}: {len(chunk)} bytes')
            await asyncio.sleep(0.3)

        print('[+] All data sent!')
        print('[*] Waiting for AC to process...')
        await asyncio.sleep(5)

        # Try to read response
        try:
            resp = await client.read_gatt_char(ONB_CHAR_UUID)
            print(f"[*] AC response: {resp.decode(errors='ignore')}")
        except Exception as e:
            print(f'[*] Could not read response: {e}')

    print()
    print('[+] Onboarding complete! AC should now connect to your WiFi.')
    print('    Check the MirAIe app or run "python3 miraie_ac_control.py discover"')
    return True

def main():
    parser = argparse.ArgumentParser(description='Panasonic AC BLE Onboarding')
    parser.add_argument('--ssid', required=True, help='Your home WiFi SSID')
    parser.add_argument('--password', required=True, help='Your home WiFi password')
    args = parser.parse_args()

    success = asyncio.run(onboard(args.ssid, args.password))
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
