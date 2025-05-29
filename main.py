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
    "give monitor recommendation only if asked. "
    "if ai is mentioned suggest core ultra series"
    "try to utilise full budget"
    "always focus on more value for money builds if user has not mentioned what type of build he wants. "
    "1. If budget < ₹10,000 or request is unrelated to PCs, respond with:\n"
    "   {'error': 'Invalid request: [reason]'}\n"
    "2. Valid builds must include: CPU, Motherboard, RAM, Storage, PSU, Case\n"
    "3. Prices must be realistic (check current Indian market)\n"
    "Respond STRICTLY in this JSON format: "
    "note that if user has not mentioned currency type treat it as Indian rupee. "
    '{"components": [{"part":"...", "model":"...", "price":"₹...", "part_image":"emoji"}], '
    '"summary": "...", "total_price": "₹..."} '
    "Use double quotes ONLY. No markdown. Only valid JSON."
)

def clean_json_response(raw_response):
    clean = re.sub(r'``````', '', raw_response)
    clean = re.sub(r'}\s*{', '},{', clean)
    clean = re.sub(r',\s*([}\]])', r'\1', clean)
    clean = clean.replace("'", '"')
    return clean.strip()

def validate_pc_request(user_input):
    budget_match = re.search(
        r'(?:₹|rs|inr)?\s*([\d,]+)(?:\.\d+)?\s*(lac|lakh|lacs|k|thousand|cr|crore|crores|million|billion)?',
        user_input,
        re.IGNORECASE
    )
    min_budget = 10000

    if budget_match:
        amount_str = budget_match.group(1).replace(',', '')  # Remove commas
        suffix = (budget_match.group(2) or '').lower()

        # Convert to numeric value
        amount = float(amount_str)
        if suffix in ['lac', 'lakh', 'lacs']:
            amount *= 100000
        elif suffix in ['k', 'thousand']:
            amount *= 1000
        elif suffix in ['cr', 'crore', 'crores']:
            amount *= 10000000
        elif suffix == 'million':
            amount *= 1000000
        elif suffix == 'billion':
            amount *= 1000000000

        budget = int(amount)
        if budget < min_budget:
            return False, f"Budget must be at least ₹{min_budget:,}"
    else:
        return False, "Could not detect valid budget amount"

    pc_keywords = r'\b(PC|computer|build|gaming|workstation|cpu|gpu|ram|motherboard)\b'
    if not re.search(pc_keywords, user_input, re.I):
        return False, "Please ask about PC configurations"
    return True, ""

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
        return redirect(url_for('index'))

    # On GET, show results if present in session, then clear for next GET
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
