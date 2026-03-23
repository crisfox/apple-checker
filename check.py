import json
import os
import urllib.request
import urllib.parse
import urllib.error
import smtplib
from email.mime.text import MIMEText

PARTS = {
    "MFXG4LL/A": "256GB Silver",
    "MFXJ4LL/A": "256GB Deep Blue",
    "MFXH4LL/A": "256GB Cosmic Orange",
    "MFXK4LL/A": "512GB Silver",
    "MFXM4LL/A": "512GB Deep Blue",
    "MFXL4LL/A": "512GB Cosmic Orange",
    "MFXN4LL/A": "1TB Silver",
    "MFXQ4LL/A": "1TB Deep Blue",
    "MFXP4LL/A": "1TB Cosmic Orange",
}

ZIP_CODE = "33139"
STATE_FILE = "state.json"


def fetch_inventory():
    params = "&".join(
        f"parts.{i}={urllib.parse.quote(part)}"
        for i, part in enumerate(PARTS.keys())
    )
    url = f"https://www.apple.com/shop/retail/pickup-message?{params}&location={ZIP_CODE}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def send_telegram(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        print("  ✓ Telegram enviado")
    except Exception as e:
        print(f"  ✗ Telegram error: {e}")


def send_email(user, password, to, subject, body):
    recipients = [r.strip() for r in to.split(",")]
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(recipients)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(user, password)
            server.sendmail(user, recipients, msg.as_string())
        print(f"  ✓ Email enviado a {len(recipients)} destinatarios")
    except Exception as e:
        print(f"  ✗ Email error: {e}")


def send_ntfy(topic, title, message):
    url = f"https://ntfy.sh/{topic}"
    req = urllib.request.Request(
        url,
        data=message.encode(),
        headers={"Title": title, "Priority": "urgent", "Tags": "apple,iphone"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        print("  ✓ ntfy enviado")
    except Exception as e:
        print(f"  ✗ ntfy error: {e}")


def notify_all(changes):
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat = os.environ.get("TELEGRAM_CHAT_ID")
    email_from = os.environ.get("EMAIL_FROM")
    email_pass = os.environ.get("EMAIL_APP_PASSWORD")
    email_to = os.environ.get("EMAIL_TO")
    ntfy_topic = os.environ.get("NTFY_TOPIC")

    lines = ["🍎 <b>iPhone 17 Pro Max — cambio de disponibilidad</b>\n"]
    plain_lines = ["iPhone 17 Pro Max — cambio de disponibilidad\n"]

    for store, part, model, old_status, new_status, quote in changes:
        emoji = "✅" if new_status == "available" else "❌"
        line = f"{emoji} <b>{model}</b>\n   📍 {store}\n   {quote}"
        plain = f"{'DISPONIBLE' if new_status == 'available' else 'AGOTADO'} {model} — {store} — {quote}"
        lines.append(line)
        plain_lines.append(plain)

    html_msg = "\n\n".join(lines)
    plain_msg = "\n".join(plain_lines)

    if telegram_token and telegram_chat:
        send_telegram(telegram_token, telegram_chat, html_msg)

    if email_from and email_pass and email_to:
        subject = "✅ iPhone disponible para pickup!" if any(
            c[3] != "available" and c[4] == "available" for c in changes
        ) else "❌ iPhone ya no disponible"
        send_email(email_from, email_pass, email_to, subject, plain_msg)

    if ntfy_topic:
        title = "iPhone disponible!" if any(
            c[3] != "available" and c[4] == "available" for c in changes
        ) else "iPhone agotado"
        send_ntfy(ntfy_topic, title, plain_msg)


def main():
    print("Chequeando inventario Apple...")
    try:
        data = fetch_inventory()
    except Exception as e:
        print(f"Error al consultar API: {e}")
        return

    stores = data.get("body", {}).get("stores", [])
    print(f"Tiendas encontradas: {len(stores)}")

    state = load_state()
    new_state = {}
    changes = []

    for store in stores:
        store_name = store["storeName"]
        city = store.get("city", "")
        distance = store.get("storeDistanceWithUnit", "")
        parts_avail = store.get("partsAvailability", {})

        for part_num, info in parts_avail.items():
            if part_num not in PARTS:
                continue

            model = PARTS[part_num]
            new_status = info.get("pickupDisplay", "unavailable")
            quote = info.get("pickupSearchQuote", "")
            key = f"{store_name}|{part_num}"

            new_state[key] = new_status
            old_status = state.get(key)

            if old_status is None:
                # Primera ejecución, solo registrar
                if new_status == "available":
                    print(f"  [INICIAL-DISPONIBLE] {model} en {store_name} ({city}) — {quote}")
                continue

            if old_status != new_status:
                label = "DISPONIBLE" if new_status == "available" else "AGOTADO"
                print(f"  [{label}] {model} en {store_name} ({city}) — {quote}")
                changes.append((f"{store_name} ({city}, {distance})", part_num, model, old_status, new_status, quote))
            else:
                status_label = "OK" if new_status == "available" else "—"
                print(f"  [{status_label}] {model} en {store_name}: {new_status}")

    if changes:
        print(f"\nEnviando {len(changes)} notificaciones...")
        notify_all(changes)
    else:
        print("\nSin cambios.")

    save_state(new_state)
    print("Estado guardado.")


if __name__ == "__main__":
    main()
