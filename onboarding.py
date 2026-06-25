#!/usr/bin/env python3
"""
Panasonic AC Onboarding Script (Updated for v01.4.25)
=====================================================

This script handles the onboarding of a new Panasonic AC to the MirAIe platform.
It connects directly to the AC's WiFi access point (192.168.4.1:443) and sends
the encrypted onboarding payload.

The crypto is the same as the original: AES-256-CBC with all-zero key+IV,
with the key+IV encrypted using the device's RSA public key.

PREREQUISITES:
  - Run 'python3 miraie_ac_control.py discover' first to get device details
  - Connect to the AC's WiFi network (it broadcasts as an AP during setup)
  - The device public key is fetched from the MirAIe API

"""

import sys
import json
import socket
import binascii

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric import padding as apadding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding


def load_saved_data():
    """Load all the data saved from the discover step."""
    try:
        with open("login_data.txt") as f:
            login_data = json.load(f)
    except FileNotFoundError:
        print("[!] login_data.txt not found. Run 'python3 miraie_ac_control.py discover' first.")
        sys.exit(1)

    try:
        with open("home_plus_user_details.txt") as f:
            home_data = json.load(f)[0]
    except FileNotFoundError:
        print("[!] home_plus_user_details.txt not found. Run discover first.")
        sys.exit(1)

    try:
        with open("ac_details.txt") as f:
            ac_data = json.load(f)[0]
    except FileNotFoundError:
        print("[!] ac_details.txt not found. Run discover first.")
        sys.exit(1)

    try:
        with open("device_public_key.txt", "rb") as f:
            device_public_key_pem = f.read()
    except FileNotFoundError:
        print("[!] device_public_key.txt not found. Run discover first.")
        sys.exit(1)

    return {
        "userId": login_data["userId"],
        "accessToken": login_data["accessToken"],
        "homeId": home_data["homeId"],
        "spaceId": home_data["spaces"][0]["spaceId"],
        "deviceId": ac_data["deviceId"],
        "deviceRegistrationTokenEncrypted": ac_data["deviceRegistrationTokenEncrypted"],
        "devicePublicKey": device_public_key_pem,
        "deviceName": ac_data.get("modelName", "Panasonic AC"),
        "macAddress": ac_data.get("macAddress", ""),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Onboard Panasonic AC to MirAIe")
    parser.add_argument("--wifi-ssid", required=True, help="Your home WiFi SSID")
    parser.add_argument("--wifi-password", required=True, help="Your home WiFi password")
    parser.add_argument("--ac-ip", default="192.168.4.1", help="AC AP IP (default: 192.168.4.1)")
    parser.add_argument("--ac-port", type=int, default=443, help="AC AP port (default: 443)")
    parser.add_argument("--bssid", default="", help="WiFi BSSID (optional)")
    args = parser.parse_args()

    data = load_saved_data()
    print("[*] Loaded saved device data:")
    print(f"    userId:     {data['userId']}")
    print(f"    homeId:     {data['homeId']}")
    print(f"    spaceId:    {data['spaceId']}")
    print(f"    deviceId:   {data['deviceId']}")
    print(f"    deviceName: {data['deviceName']}")

    # Build onboarding payload
    onboarding_payload = {
        "BSSID": args.bssid or args.wifi_ssid,
        "deviceName": data["deviceName"],
        "homeId": data["homeId"],
        "useProd": "1",
        "spaceId": data["spaceId"],
        "userId": data["userId"],
        "wifipassword": args.wifi_password,
        "wifissid": args.wifi_ssid,
    }

    print(f"\n[*] Onboarding payload (WiFi: {args.wifi_ssid}):")
    print(json.dumps(onboarding_payload, indent=2))

    # Crypto: AES-256-CBC with all-zero key and IV
    key = b'\x00' * 32
    iv = b'\x00' * 16

    # Encrypt payload with AES
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    padder = padding.PKCS7(128).padder()
    plaintext = json.dumps(onboarding_payload).encode("utf-8")
    padded = padder.update(plaintext) + padder.finalize()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    payload_hex = binascii.hexlify(ciphertext).decode("ascii")

    # Encrypt key and IV with device's RSA public key
    device_public_key = serialization.load_pem_public_key(data["devicePublicKey"])
    encrypted_key = device_public_key.encrypt(key, apadding.PKCS1v15())
    encrypted_key_hex = binascii.hexlify(encrypted_key).decode("ascii")
    encrypted_iv = device_public_key.encrypt(iv, apadding.PKCS1v15())
    encrypted_iv_hex = binascii.hexlify(encrypted_iv).decode("ascii")

    # Build final encrypted payload
    encrypted_payload = {
        "deviceRegistrationToken": data["deviceRegistrationTokenEncrypted"],
        "iv": encrypted_iv_hex,
        "key": encrypted_key_hex,
        "payload": payload_hex,
        "version": "1.0",
    }
    final_payload = json.dumps(encrypted_payload).encode("utf-8")

    # Send to AC
    print(f"\n[*] Connecting to AC at {args.ac_ip}:{args.ac_port}...")
    initial_msg = b'{"type": "ob", "size": %d}' % len(final_payload)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(15)
        try:
            s.connect((args.ac_ip, args.ac_port))
            print("[+] Connected to AC!")

            # Send initial handshake
            s.sendall(initial_msg)
            print(f"[*] Sent: {initial_msg}")

            # Receive ACK
            resp = s.recv(10240)
            print(f"[*] Received: {resp}")

            # Send encrypted payload
            s.sendall(final_payload)
            print(f"[*] Sent encrypted payload ({len(final_payload)} bytes)")

            # Receive final response
            resp = s.recv(10240)
            print(f"[*] Received: {resp}")

            try:
                resp_json = json.loads(resp)
                code = resp_json.get("code")
                if code == 200 or code == 201:
                    print("[+] Onboarding successful! AC should now connect to your WiFi.")
                elif code == 116:
                    print("[!] Error 116: Device already added (AONB - Already Onboarded)")
                    print("    If this is your device, it may already be registered.")
                    print("    Try removing it from the MirAIe app and retrying.")
                else:
                    print(f"[*] Response code: {code} - {resp_json.get('message', '')}")
            except json.JSONDecodeError:
                print(f"[*] Raw response: {resp}")

        except socket.timeout:
            print("[!] Connection timed out. Make sure:")
            print("    1. The AC is in pairing mode (WiFi LED blinking)")
            print("    2. You are connected to the AC's WiFi network")
            print("    3. The AC IP is correct (usually 192.168.4.1)")
        except ConnectionRefusedError:
            print(f"[!] Connection refused at {args.ac_ip}:{args.ac_port}")
            print("    Make sure AC is in pairing mode and you're on its WiFi.")


if __name__ == "__main__":
    main()
