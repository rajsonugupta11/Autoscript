import aiohttp
import asyncio
import brotli
import gzip
import random
import re
import os
from colorama import init as colorama_init, Fore, Style
from flask import Flask
from threading import Thread

# -----------------------------------------
# CONFIG SECTION
# -----------------------------------------
colorama_init(autoreset=True)

# 👇 Replace YOUR_USERNAME with your GitHub username and repo name
GITHUB_TOKENS_URL = "https://raw.githubusercontent.com/YOUR_USERNAME/kaisar-bot-data/main/tokens.txt"
PING_PORT = int(os.getenv("PORT", 8080))  # Railway sets PORT automatically

BALANCE_URL = "https://zero-api.kaisar.io/user/balances?symbol=point"
SPIN_URL = "https://zero-api.kaisar.io/lucky/spin"
CONVERT_URL = "https://zero-api.kaisar.io/lucky/convert"

timeout = aiohttp.ClientTimeout(total=10)

ACCOUNT_COLORS = [
    Fore.RED, Fore.GREEN, Fore.YELLOW, Fore.BLUE,
    Fore.MAGENTA, Fore.CYAN, Fore.LIGHTRED_EX, Fore.LIGHTGREEN_EX,
    Fore.LIGHTYELLOW_EX, Fore.LIGHTBLUE_EX, Fore.LIGHTMAGENTA_EX, Fore.LIGHTCYAN_EX
]

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/134.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/116.0.5845.97 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_1) Chrome/116.0.5845.97 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; SM-G991B) Chrome/115.0.5790.171 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) Chrome/115.0.5790.171 Mobile Safari/604.1",
]

# -----------------------------------------
# KEEP ALIVE SERVER (For Railway ping)
# -----------------------------------------
app = Flask('')

@app.route('/')
def home():
    return "✅ Bot is running!"

def run_server():
    app.run(host='0.0.0.0', port=PING_PORT)

def keep_alive():
    Thread(target=run_server).start()

# -----------------------------------------
# MAIN LOGIC FUNCTIONS
# -----------------------------------------

def get_headers(token):
    return {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br",
        "authorization": f"Bearer {token.strip()}",
        "content-type": "application/json",
        "origin": "https://zero.kaisar.io",
        "referer": "https://zero.kaisar.io/",
        "user-agent": random.choice(USER_AGENTS),
    }

async def decode_response(resp):
    raw_data = await resp.read()
    encoding = resp.headers.get("content-encoding", "")
    try:
        if "br" in encoding:
            raw_data = brotli.decompress(raw_data)
        elif "gzip" in encoding:
            raw_data = gzip.decompress(raw_data)
    except:
        pass
    return raw_data.decode("utf-8", errors="ignore")

async def fetch_tokens():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(GITHUB_TOKENS_URL) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    tokens = [t.strip() for t in text.splitlines() if t.strip()]
                    print(f"{Fore.GREEN}✅ Tokens fetched: {len(tokens)}{Style.RESET_ALL}")
                    return tokens
    except Exception as e:
        print(f"{Fore.RED}Failed to fetch tokens: {e}{Style.RESET_ALL}")
    return []

async def is_token_valid(session, headers):
    try:
        async with session.get(BALANCE_URL, headers=headers) as resp:
            return resp.status == 200
    except:
        return False

async def check_balance(session, headers, name, color):
    try:
        async with session.get(BALANCE_URL, headers=headers) as resp:
            decoded = await decode_response(resp)
            match = re.search(r'"balance":"?([\d.]+)"?', decoded)
            if match:
                balance = float(match.group(1))
                print(f"{color}[{name}] 💰 Balance: {Fore.YELLOW}{balance}{Style.RESET_ALL}")
                return balance
    except:
        pass
    return None

async def buy_ticket(session, headers, count, name, color):
    try:
        if count <= 0:
            return
        await session.post(CONVERT_URL, headers=headers, json={})
        print(f"{color}[{name}] 🎟 Ticket purchased.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{color}[{name}] {Fore.RED}Ticket buy error: {e}{Style.RESET_ALL}")

async def spin(session, headers, sem):
    async with sem:
        try:
            headers["user-agent"] = random.choice(USER_AGENTS)
            async with session.post(SPIN_URL, headers=headers, json={}) as resp:
                return resp.status
        except:
            return None

async def worker(token, target, name, color):
    headers = get_headers(token)
    sem = asyncio.Semaphore(100)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        if not await is_token_valid(session, headers):
            print(f"{color}[{name}] Invalid token — skipping.{Style.RESET_ALL}")
            return

        while True:
            balance = await check_balance(session, headers, name, color)
            if balance is None:
                await asyncio.sleep(5)
                continue

            if balance >= target:
                print(f"{color}[{name}] 🎯 Target reached!{Style.RESET_ALL}")
                break

            if balance >= 300:
                await buy_ticket(session, headers, 1, name, color)
            else:
                print(f"{color}[{name}] Waiting (low balance)...{Style.RESET_ALL}")
                await asyncio.sleep(50)
                continue

            tasks = [spin(session, headers, sem) for _ in range(300)]
            results = await asyncio.gather(*tasks)
            hits = sum(1 for r in results if r == 200)
            print(f"{color}[{name}] 🎰 Spins done: {hits}{Style.RESET_ALL}")
            await asyncio.sleep(1)

# -----------------------------------------
# TOKEN REFRESHER + MAIN RUNNER
# -----------------------------------------
async def token_refresher():
    global TOKENS
    while True:
        TOKENS = await fetch_tokens()
        await asyncio.sleep(3600)  # Refresh every 1 hour

async def main():
    keep_alive()
    print(f"{Fore.CYAN}🚀 Bot started with auto-ping & GitHub tokens.{Style.RESET_ALL}")

    TOKENS = await fetch_tokens()
    if not TOKENS:
        print(f"{Fore.RED}No tokens found. Exiting...{Style.RESET_ALL}")
        return

    target = float(os.getenv("TARGET_POINTS", 1000))  # default target = 1000
    tasks = []
    for i, token in enumerate(TOKENS):
        color = ACCOUNT_COLORS[i % len(ACCOUNT_COLORS)]
        tasks.append(worker(token, target, f"Account #{i+1}", color))

    await asyncio.gather(*tasks, token_refresher())

asyncio.run(main())
                  
