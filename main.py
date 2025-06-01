from flask import Flask, render_template, request, redirect, url_for, session
from openai import OpenAI
import json
import re
import os
  # Replace with your actual key
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY")


app = Flask(__name__,static_folder='static')
app.secret_key = os.getenv("GEN_AI_KEY")  # Needed for session

client = OpenAI(api_key=PERPLEXITY_API_KEY, base_url="https://api.perplexity.ai")

SYSTEM_PROMPT = (
    "You are a PC builder. Follow STRICTLY:\n"
    '"stricty give response like'
    "Response Format:\n"
    '''{
  "components": [
    {"part": "CPU", "model": "AMD Ryzen 7 7800X3D", "price": "₹37,500", "part_image": "💻"},
    {"part": "GPU", "model": "ZOTAC RTX 5080 Trinity", "price": "₹1,12,000", "part_image": "🖥️"},
    {"part": "Motherboard", "model": "MSI B650 Tomahawk WiFi", "price": "₹22,000", "part_image": "🖥️"},
    {"part": "RAM", "model": "32GB Corsair Vengeance DDR5-6000", "price": "₹19,800", "part_image": "📦"},
    {"part": "Storage", "model": "1TB WD Black SN850X", "price": "₹8,200", "part_image": "💾"},
    {"part": "PSU", "model": "Deepcool PM850D 850W Gold", "price": "₹7,800", "part_image": "🔌"},
    {"part": "Case", "model": "Lian Li Lancool 216", "price": "₹8,500", "part_image": "📦"}
  ],
  "summary": "High-performance gaming PC...",
  "total_price": "₹2,15,800"
}'''
    "1. Core Components (MUST include all 6):\n"
    "   - CPU\n"
    "   - Motherboard\n"
    "   - RAM\n"
    "   - Storage\n"
    "   - PSU\n"
    "   - Case\n"
    "2. GPU Rules:\n"
    "   - Budget ≥₹3,00,000: RTX 5090 (₹3.3L-₹4.0L)\n"
    "   - Budget ≥₹1,50,000: RTX 5080 (₹1.0L-₹1.6L)\n"
    "   - Budget ≥₹80,000: RTX 5070 Ti\n"
    "   - Never suggest RTX 5090 below ₹3,30,000\n"
    "3. CPU Cooler Rules:\n"
    "   - Budget ≥₹1,00,000: Include 360mm AIO\n"
    "   - Budget ≥₹50,000: Include air cooler\n"
    "   - Budget <₹50,000: Use stock cooler (do not list)\n"
    "4. Accessories:\n"
    "   - Add monitor/keyboard/mouse ONLY if mentioned\n"
    "   - Never include OS/licenses unless explicitly asked\n"
    "5. Price Guidelines (Indian Market):\n"
    "   - RTX 5090: ₹3,30,000-₹4,00,000\n"
    "   - RTX 5080: ₹1,00,000-₹1,60,000\n"
    "   - RTX 5070 Ti: ₹80,000-₹1,00,000\n"
    "   - DDR5 32GB: ₹18,000-₹25,000\n"
    "   - 1TB Gen4 SSD: ₹7,000-₹9,000\n"
    
    "\nStrict Rules:\n"
    "- Use ONLY double quotes\n"
    "- Prices MUST match current Indian rates and treat user input as indian currency if another currency not mentioned\n"
    "- Never exceed stated budget\n"
    "- part_image emojis: 💻(CPU), 🖥️(MB/GPU), 📦(RAM/Case), 💾(Storage), 🔌(PSU), ❄️(Cooler)\n"
    "- If error occurs, return {'error':'...'} with reason"
)




def clean_json_response(raw_response):
    clean = re.sub(r'``````', '', raw_response)
    clean = re.sub(r'}\s*{', '},{', clean)
    clean = re.sub(r',\s*([}\]])', r'\1', clean)
    clean = clean.replace("'", '"')
    return clean.strip()


def validate_pc_request(user_input):
    # Improved budget detection that requires currency or budget keywords
    budget_pattern = (
        r'(?:budget|under|around|₹|rs|inr)\s*'  # Requires budget-related keywords
        r'(\d[\d,]*)'  # Amount with optional commas
        r'\s*(lac|lakh|lacs|k|thousand|cr|crore|crores|million|billion)?\b'
    )
    budget_match = re.search(budget_pattern,user_input,re.IGNORECASE)

    min_budget = 10000
    detected_budget = None

    if budget_match:
        amount_str = budget_match.group(1).replace(',','')
        suffix = (budget_match.group(2) or '').lower()

        try:
            amount = float(amount_str)
            # Convert suffixes to actual values
            multiplier = 1
            if suffix in ['lac','lakh','lacs']:
                multiplier = 100000
            elif suffix in ['k','thousand']:
                multiplier = 1000
            elif suffix in ['cr','crore','crores']:
                multiplier = 10000000
            elif suffix == 'million':
                multiplier = 1000000
            elif suffix == 'billion':
                multiplier = 1000000000

            detected_budget = int(amount * multiplier)

            if detected_budget < min_budget:
                return False,f"Budget must be at least ₹{min_budget:,}"

        except ValueError:
            detected_budget = None

    # Check for PC components without budget
    pc_component_keywords = r'\b(PC|computer|build|gaming|workstation|cpu|gpu|ram|motherboard|rtx|ryzen|core i\d|ssd|hdd|psu)\b'
    if not re.search(pc_component_keywords,user_input,re.I):
        return False,"Please ask about PC configurations"

    # Allow requests without explicit budget
    return True,""


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        user_input = request.form.get("content", "").strip()
        is_valid, error_msg = validate_pc_request(user_input)
        session['user_input'] = user_input  # Save for redisplay if error
        session['components'] = []
        session['summary'] = ""
        session['total_price'] = ""
        session['error'] = ""
        if not is_valid:
            session['error'] = error_msg
        else:
            try:
                response = client.chat.completions.create(
                    model="sonar-pro",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_input}
                    ]
                )
                raw_answer = response.choices[0].message.content
                print(raw_answer)
                clean_answer = clean_json_response(raw_answer)
                data = json.loads(clean_answer)
                if 'error' in data:
                    session['error'] = data['error']
                else:
                    session['components'] = data.get("components", [])
                    session['summary'] = data.get("summary", "")
                    session['total_price'] = data.get("total_price", "")
            except Exception as e:
                session['error'] = f"Sorry, there was a problem processing your request. ({str(e)})"
        return redirect(url_for('index') + "#components-section")

    components = session.pop('components', [])
    summary = session.pop('summary', "")
    total_price = session.pop('total_price', "")
    error = session.pop('error', "")
    user_input = session.pop('user_input', "")

    return render_template(
        "index.html",
        components=components,
        summary=summary,
        total_price=total_price,
        error=error,
        user_input=user_input
    )

if __name__ == "__main__":
    app.run()
