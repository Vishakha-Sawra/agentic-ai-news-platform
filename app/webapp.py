from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import timedelta
import os
import json
import re
import requests
from dotenv import load_dotenv

# Import new modules
from app.database import get_db, init_database
from app.auth import authenticate_user, create_access_token, get_current_active_user, create_user, ACCESS_TOKEN_EXPIRE_MINUTES
from app.models import User, Category, Article, UserSubscription, DigestLog
from app.schemas import *
from services.digest_service import digest_service
from services.categorization_service import categorizer

load_dotenv()

app = FastAPI(title="Tech News Digest API", description="Personalized tech news digests and notifications")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_database()
    # Sync existing articles to database
    categorizer.sync_articles_from_files()

SUMMARIES_DIR = 'data/summaries/'
PLACEHOLDER_IMAGE = 'https://via.placeholder.com/600x300?text=No+Image'

CARD_CSS = """
<style>
body {
    font-family: 'Segoe UI', Arial, sans-serif;
    background: #f7f7f9;
    margin: 0;
    padding: 0;
}
.container {
    max-width: 1200px;
    margin: 40px auto;
    padding: 0 16px;
}
.grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 32px;
}
.card {
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.07);
    overflow: hidden;
    transition: transform 0.1s, box-shadow 0.1s;
    cursor: pointer;
    text-decoration: none;
    color: inherit;
    display: flex;
    flex-direction: column;
    height: 100%;
}
.card:hover {
    transform: translateY(-4px) scale(1.02);
    box-shadow: 0 6px 24px rgba(0,0,0,0.13);
}
.card img {
    width: 100%;
    height: 180px;
    object-fit: cover;
    background: #eee;
}
.card-content {
    padding: 20px 18px 18px 18px;
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
}
.card-title {
    font-size: 1.2rem;
    font-weight: 600;
    margin: 0 0 10px 0;
    color: #2d3748;
}
.card-date {
    font-size: 0.95rem;
    color: #718096;
    margin-bottom: 10px;
}
.card-llm-summary {
    background: #e6f4ea;
    color: #176148;
    border-radius: 6px;
    padding: 10px 12px;
    margin-bottom: 12px;
    font-size: 1rem;
    font-style: italic;
    border-left: 4px solid #38b2ac;
}
.card-llm-label {
    font-size: 0.92rem;
    font-weight: 600;
    color: #176148;
    margin-bottom: 4px;
    letter-spacing: 0.5px;
}
.card-summary {
    font-size: 1rem;
    color: #444;
    margin-bottom: 0;
    flex: 1 1 auto;
}
/* Chat UI styles */
#chatbox {
    max-width: 700px;
    margin: 40px auto 0 auto;
    background: #fff;
    border-radius: 10px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.07);
    padding: 24px 20px 16px 20px;
}
#chatlog {
    min-height: 60px;
    margin-bottom: 16px;
    font-size: 1.08rem;
    color: #2d3748;
}
#userinput {
    width: 80%;
    padding: 10px;
    font-size: 1rem;
    border-radius: 6px;
    border: 1px solid #cbd5e1;
    margin-right: 8px;
}
#sendbtn {
    padding: 10px 18px;
    font-size: 1rem;
    border-radius: 6px;
    border: none;
    background: #38b2ac;
    color: #fff;
    cursor: pointer;
    transition: background 0.2s;
}
#sendbtn:hover {
    background: #176148;
}
</style>
"""

# Helper: Get LLM answer from Together AI

def get_llm_answer_together(question, articles):
    api_key = os.getenv("TOGETHER_API_KEY")
    if not api_key:
        return "Together AI API key not set."
    # Compose context from top 5 articles (title + llm_summary)
    context = "\n\n".join([
        f"Title: {a['title']}\nAI Summary: {a.get('llm_summary','')}" for a in articles[:5]
    ])
    prompt = (
        f"You are an expert tech news assistant.\n"
        f"Here are some recent tech news stories:\n{context}\n\n"
        f"User question: {question}\n"
        f"Answer the user's question using only the information above."
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "max_tokens": 200,
        "temperature": 0.7,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    try:
        response = requests.post(
            "https://api.together.xyz/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Together AI API error: {e}"

def get_keywords(text):
    # Simple keyword extraction: split on non-word chars, lowercase, remove stopwords
    stopwords = set(['the','is','at','which','on','a','an','and','or','for','to','of','in','with','by','as','from','that','this','it','are','be','was','were','has','had','have','but','not','if','then','so','do','does','did','can','will','just','about','into','over','after','before','more','less','than','up','out','off','no','yes','you','i','we','they','he','she','his','her','their','our','my','your'])
    words = re.findall(r'\w+', text.lower())
    return [w for w in words if w not in stopwords and len(w) > 2]

def select_relevant_articles(question, articles, top_n=5):
    q_keywords = set(get_keywords(question))
    scored = []
    for a in articles:
        text = f"{a.get('title','')} {a.get('summary','')} {a.get('llm_summary','')}"
        a_keywords = set(get_keywords(text))
        score = len(q_keywords & a_keywords)
        scored.append((score, a))
    scored.sort(reverse=True, key=lambda x: x[0])
    # If all scores are zero, fallback to most recent
    if scored and scored[0][0] == 0:
        return articles[:top_n]
    return [a for score, a in scored[:top_n]]

@app.post("/auth/register", response_model=UserResponse)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user"""
    try:
        user = create_user(db, user_data.email, user_data.password, user_data.full_name)
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/auth/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login and get access token"""
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """Get current user information"""
    return current_user

# Category endpoints
@app.get("/categories", response_model=List[CategoryResponse])
async def get_categories(db: Session = Depends(get_db)):
    """Get all available categories"""
    categories = db.query(Category).all()
    return categories

# User preferences endpoints
@app.get("/preferences", response_model=DigestPreferences)
async def get_preferences(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Get user's digest preferences"""
    user_category_ids = [cat.id for cat in current_user.interests]
    return DigestPreferences(
        daily_digest_enabled=current_user.daily_digest_enabled,
        weekly_digest_enabled=current_user.weekly_digest_enabled,
        instant_notifications=current_user.instant_notifications,
        digest_time=current_user.digest_time,
        time_zone=current_user.time_zone,
        interested_categories=user_category_ids
    )

@app.put("/preferences", response_model=UserResponse)
async def update_preferences(
    preferences: PreferencesUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update user's digest preferences"""
    
    # Update basic preferences
    if preferences.daily_digest_enabled is not None:
        current_user.daily_digest_enabled = preferences.daily_digest_enabled
    if preferences.weekly_digest_enabled is not None:
        current_user.weekly_digest_enabled = preferences.weekly_digest_enabled
    if preferences.instant_notifications is not None:
        current_user.instant_notifications = preferences.instant_notifications
    if preferences.digest_time is not None:
        current_user.digest_time = preferences.digest_time
    if preferences.time_zone is not None:
        current_user.time_zone = preferences.time_zone
    
    # Update interested categories
    if preferences.interested_categories is not None:
        # Clear existing interests
        current_user.interests.clear()
        # Add new interests
        for category_id in preferences.interested_categories:
            category = db.query(Category).filter(Category.id == category_id).first()
            if category:
                current_user.interests.append(category)
    
    db.commit()
    db.refresh(current_user)
    return current_user

# Subscription endpoints
@app.post("/subscriptions", response_model=SubscriptionResponse)
async def create_subscription(
    subscription: SubscriptionCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new subscription"""
    db_subscription = UserSubscription(
        user_id=current_user.id,
        subscription_type=subscription.subscription_type,
        category_id=subscription.category_id,
        keywords=subscription.keywords
    )
    db.add(db_subscription)
    db.commit()
    db.refresh(db_subscription)
    return db_subscription

@app.get("/subscriptions", response_model=List[SubscriptionResponse])
async def get_subscriptions(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get user's subscriptions"""
    return current_user.subscriptions

@app.delete("/subscriptions/{subscription_id}")
async def delete_subscription(
    subscription_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a subscription"""
    subscription = db.query(UserSubscription).filter(
        UserSubscription.id == subscription_id,
        UserSubscription.user_id == current_user.id
    ).first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    db.delete(subscription)
    db.commit()
    return {"message": "Subscription deleted"}

# Digest endpoints
@app.get("/digest/preview", response_model=DigestPreview)
async def preview_digest(
    digest_type: str = "daily",
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Preview digest content for the user"""
    days_back = 1 if digest_type == "daily" else 7
    max_articles = 5 if digest_type == "daily" else 10
    
    articles_by_category = digest_service.get_articles_for_user(
        db, current_user, days_back, max_articles
    )
    
    total_articles = sum(len(articles) for articles in articles_by_category.values())
    
    return DigestPreview(
        total_articles=total_articles,
        categories=articles_by_category,
        digest_type=digest_type
    )

@app.post("/digest/send")
async def send_digest_now(
    digest_type: str = "daily",
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Send digest immediately to the current user"""
    if digest_type == "daily":
        success = digest_service.generate_daily_digest(db, current_user)
    else:
        success = digest_service.generate_weekly_digest(db, current_user)
    
    if success:
        return {"message": f"{digest_type.title()} digest sent successfully"}
    else:
        raise HTTPException(status_code=400, detail="Failed to send digest")

@app.get("/digest/history", response_model=List[DigestLogResponse])
async def get_digest_history(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get user's digest history"""
    digest_logs = (db.query(DigestLog)
                   .filter(DigestLog.user_id == current_user.id)
                   .order_by(DigestLog.sent_at.desc())
                   .limit(20)
                   .all())
    return digest_logs

# Articles endpoints
@app.get("/articles", response_model=List[ArticleResponse])
async def get_articles(
    category_id: Optional[int] = None,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Get articles, optionally filtered by category"""
    query = db.query(Article)
    
    if category_id:
        query = query.join(ArticleCategory).filter(ArticleCategory.category_id == category_id)
    
    articles = query.order_by(Article.created_at.desc()).limit(limit).all()
    return articles

@app.get("/articles/personalized", response_model=List[ArticleResponse])
async def get_personalized_articles(
    current_user: User = Depends(get_current_active_user),
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Get personalized articles for the current user"""
    articles_by_category = digest_service.get_articles_for_user(db, current_user, days_back=7, max_articles_per_category=limit//3)
    
    # Flatten the articles
    all_articles = []
    for articles in articles_by_category.values():
        all_articles.extend(articles)
    
    # Remove duplicates and sort by creation date
    seen = set()
    unique_articles = []
    for article in sorted(all_articles, key=lambda x: x.created_at, reverse=True):
        if article.id not in seen:
            seen.add(article.id)
            unique_articles.append(article)
    
    return unique_articles[:limit]

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve the user dashboard for managing digest preferences"""
    with open("digest_dashboard.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.get('/', response_class=HTMLResponse)
def read_cards():
    articles = []
    if os.path.exists(SUMMARIES_DIR):
        for filename in sorted(os.listdir(SUMMARIES_DIR), reverse=True):
            if filename.endswith('.json'):
                with open(os.path.join(SUMMARIES_DIR, filename), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                articles.append({
                    'title': data.get('title', ''),
                    'link': data.get('link', ''),
                    'summary': data.get('summary', ''),
                    'llm_summary': data.get('llm_summary', ''),
                    'published': data.get('published', ''),
                    'image_url': data.get('image_url') or PLACEHOLDER_IMAGE
                })
    html = f'<html><head><title>Tech News Summaries</title>{CARD_CSS}</head><body>'
    html += '<div class="container">'
    html += '<div style="text-align:center; margin-bottom:32px;">'
    html += '<h1 style="color:#2d3748; margin-bottom:16px;">🚀 Tech News Digest</h1>'
    html += '<p style="color:#666; font-size:16px;">Personalized tech news summaries powered by AI</p>'
    html += '<div style="margin-top:20px;">'
    html += '<button onclick="showAuthModal()" style="background:#667eea; color:white; padding:12px 24px; border:none; border-radius:6px; font-size:16px; cursor:pointer; margin-right:10px;">🔔 Subscribe to Digests</button>'
    html += '<button onclick="window.location.href=\'/dashboard\'" style="background:#48bb78; color:white; padding:12px 24px; border:none; border-radius:6px; font-size:16px; cursor:pointer; margin-right:10px;">⚙️ Manage Preferences</button>'
    html += '<button onclick="showAPIInfo()" style="background:#38b2ac; color:white; padding:12px 24px; border:none; border-radius:6px; font-size:16px; cursor:pointer;">📊 For Developers</button>'
    html += '</div>'
    html += '</div>'
    html += '<div class="grid">'
    for article in articles:
        html += f'''
         <a class="card" href="{article['link']}" target="_blank">
             <img src="{article['image_url']}" alt="Article image">
             <div class="card-content">
                 <div class="card-title">{article['title']}</div>
                 <div class="card-date">{article['published']}</div>
                 {f'<div class="card-llm-label">AI Summary</div><div class="card-llm-summary">{article["llm_summary"]}</div>' if article['llm_summary'] else ''}
                 <div class="card-summary">{article['summary'][:220]}{'...' if len(article['summary']) > 220 else ''}</div>
             </div>
         </a>
        '''
    html += '''
    
    <!-- Auth Modal -->
    <div id="authModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1000;">
      <div style="position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); background:white; padding:30px; border-radius:10px; max-width:400px; width:90%;">
        <h2 style="margin:0 0 20px 0; color:#2d3748;">🔔 Subscribe to Personalized Digests</h2>
        <div id="authTabs" style="margin-bottom:20px;">
          <button onclick="showRegister()" id="registerTab" style="background:#667eea; color:white; padding:8px 16px; border:none; border-radius:4px; margin-right:8px; cursor:pointer;">Register</button>
          <button onclick="showLogin()" id="loginTab" style="background:#e2e8f0; color:#4a5568; padding:8px 16px; border:none; border-radius:4px; cursor:pointer;">Login</button>
        </div>
        <div id="registerForm">
          <input type="email" id="regEmail" placeholder="Email" style="width:100%; padding:10px; margin-bottom:10px; border:1px solid #cbd5e1; border-radius:4px;">
          <input type="password" id="regPassword" placeholder="Password" style="width:100%; padding:10px; margin-bottom:10px; border:1px solid #cbd5e1; border-radius:4px;">
          <input type="text" id="regName" placeholder="Full Name (optional)" style="width:100%; padding:10px; margin-bottom:15px; border:1px solid #cbd5e1; border-radius:4px;">
          <button onclick="register()" style="background:#667eea; color:white; padding:12px 24px; border:none; border-radius:6px; width:100%; cursor:pointer;">Create Account & Subscribe</button>
        </div>
        <div id="loginForm" style="display:none;">
          <input type="email" id="loginEmail" placeholder="Email" style="width:100%; padding:10px; margin-bottom:10px; border:1px solid #cbd5e1; border-radius:4px;">
          <input type="password" id="loginPassword" placeholder="Password" style="width:100%; padding:10px; margin-bottom:15px; border:1px solid #cbd5e1; border-radius:4px;">
          <button onclick="login()" style="background:#667eea; color:white; padding:12px 24px; border:none; border-radius:6px; width:100%; cursor:pointer;">Login</button>
        </div>
        <button onclick="closeAuthModal()" style="position:absolute; top:10px; right:15px; background:none; border:none; font-size:20px; cursor:pointer;">×</button>
        <div id="authMessage" style="margin-top:15px; padding:10px; border-radius:4px; display:none;"></div>
      </div>
    </div>
    
    <!-- API Info Modal -->
    <div id="apiModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1000;">
      <div style="position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); background:white; padding:30px; border-radius:10px; max-width:600px; width:90%; max-height:80%; overflow-y:auto;">
        <h2 style="margin:0 0 20px 0; color:#2d3748;">📊 Developer API</h2>
        <div style="background:#f8f9fa; padding:15px; border-radius:6px; margin-bottom:15px;">
          <h3 style="margin:0 0 10px 0; color:#4a5568;">Base URL:</h3>
          <code style="background:#e2e8f0; padding:4px 8px; border-radius:4px;">http://localhost:8000</code>
        </div>
        <div style="margin-bottom:20px;">
          <h3 style="color:#4a5568;">Key Endpoints:</h3>
          <ul style="list-style-type:none; padding:0;">
            <li style="margin:8px 0; padding:8px; background:#f8f9fa; border-radius:4px;"><strong>POST /auth/register</strong> - Register new user</li>
            <li style="margin:8px 0; padding:8px; background:#f8f9fa; border-radius:4px;"><strong>GET /preferences</strong> - Get digest preferences</li>
            <li style="margin:8px 0; padding:8px; background:#f8f9fa; border-radius:4px;"><strong>PUT /preferences</strong> - Update digest preferences</li>
            <li style="margin:8px 0; padding:8px; background:#f8f9fa; border-radius:4px;"><strong>GET /digest/preview</strong> - Preview personalized digest</li>
            <li style="margin:8px 0; padding:8px; background:#f8f9fa; border-radius:4px;"><strong>GET /articles/personalized</strong> - Get personalized articles</li>
          </ul>
        </div>
        <p style="color:#666; font-size:14px;">Visit <code>/docs</code> for interactive API documentation</p>
        <button onclick="closeAPIModal()" style="position:absolute; top:10px; right:15px; background:none; border:none; font-size:20px; cursor:pointer;">×</button>
      </div>
    </div>
    
    <script>
    const chatlog = document.getElementById('chatlog');
    const userinput = document.getElementById('userinput');
    const sendbtn = document.getElementById('sendbtn');
    sendbtn.onclick = sendMsg;
    userinput.addEventListener('keydown', function(e) { if (e.key === 'Enter') sendMsg(); });
    
    function sendMsg() {
      const msg = userinput.value.trim();
      if (!msg) return;
      chatlog.innerHTML += `<div><b>You:</b> ${msg}</div>`;
      userinput.value = '';
      fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: msg })
      })
      .then(r => r.json())
      .then(data => {
        chatlog.innerHTML += `<div><b>Agent:</b> ${data.answer}</div>`;
        chatlog.scrollTop = chatlog.scrollHeight;
      })
      .catch(() => {
        chatlog.innerHTML += `<div style='color:red'><b>Agent:</b> Error getting answer.</div>`;
      });
    }
    
    // Modal functions
    function showAuthModal() {
      document.getElementById('authModal').style.display = 'block';
      showRegister();
    }
    
    function closeAuthModal() {
      document.getElementById('authModal').style.display = 'none';
    }
    
    function showAPIInfo() {
      document.getElementById('apiModal').style.display = 'block';
    }
    
    function closeAPIModal() {
      document.getElementById('apiModal').style.display = 'none';
    }
    
    function showRegister() {
      document.getElementById('registerForm').style.display = 'block';
      document.getElementById('loginForm').style.display = 'none';
      document.getElementById('registerTab').style.background = '#667eea';
      document.getElementById('registerTab').style.color = 'white';
      document.getElementById('loginTab').style.background = '#e2e8f0';
      document.getElementById('loginTab').style.color = '#4a5568';
    }
    
    function showLogin() {
      document.getElementById('registerForm').style.display = 'none';
      document.getElementById('loginForm').style.display = 'block';
      document.getElementById('loginTab').style.background = '#667eea';
      document.getElementById('loginTab').style.color = 'white';
      document.getElementById('registerTab').style.background = '#e2e8f0';
      document.getElementById('registerTab').style.color = '#4a5568';
    }
    
    function showMessage(text, isError = false) {
      const messageDiv = document.getElementById('authMessage');
      messageDiv.style.display = 'block';
      messageDiv.style.background = isError ? '#fed7d7' : '#c6f6d5';
      messageDiv.style.color = isError ? '#c53030' : '#25543e';
      messageDiv.innerHTML = text;
    }
    
    async function register() {
      const email = document.getElementById('regEmail').value;
      const password = document.getElementById('regPassword').value;
      const name = document.getElementById('regName').value;
      
      if (!email || !password) {
        showMessage('Please fill in email and password', true);
        return;
      }
      
      try {
        const response = await fetch('/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password, full_name: name })
        });
        
        if (response.ok) {
          showMessage('Account created successfully! Redirecting to your dashboard...');
          setTimeout(() => {
            window.location.href = '/dashboard';
          }, 2000);
        } else {
          const error = await response.json();
          showMessage(error.detail || 'Registration failed', true);
        }
      } catch (error) {
        showMessage('Network error. Please try again.', true);
      }
    }
    
    async function login() {
      const email = document.getElementById('loginEmail').value;
      const password = document.getElementById('loginPassword').value;
      
      if (!email || !password) {
        showMessage('Please fill in email and password', true);
        return;
      }
      
      try {
        const formData = new FormData();
        formData.append('username', email);
        formData.append('password', password);
        
        const response = await fetch('/auth/token', {
          method: 'POST',
          body: formData
        });
        
        if (response.ok) {
          const data = await response.json();
          localStorage.setItem('authToken', data.access_token);
          showMessage('Login successful! Redirecting to your dashboard...');
          setTimeout(() => {
            window.location.href = '/dashboard';
          }, 2000);
        } else {
          showMessage('Invalid email or password', true);
        }
      } catch (error) {
        showMessage('Network error. Please try again.', true);
      }
    }
    </script>
    '''
    return html

@app.get("/chat", response_class=HTMLResponse)
def chat_page():
    html = '''
    <html>
    <head>
        <title>Chat Assistant</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            body { 
                font-family: Arial, sans-serif; 
                margin: 0; 
                background: #f5f5f5; 
                display: flex; 
                flex-direction: column; 
                height: 100vh; 
            }
            #chatbox { 
                flex: 1; 
                display: flex; 
                flex-direction: column; 
                max-width: 700px; 
                margin: auto; 
                width: 100%; 
                overflow: hidden;
                margin-bottom: 20px;
            }
            #chatlog { 
                flex: 1; 
                padding: 20px; 
                overflow-y: auto; 
                font-size: 1.08rem; 
                color: #2d3748; 
            }
            .msg { margin-bottom: 12px; }
            .user { text-align: right; color: #1a202c; }
            .agent { text-align: left; color: #2d3748; }
            .bubble {
                display: inline-block;
                padding: 10px 14px;
                border-radius: 18px;
                max-width: 80%;
                word-wrap: break-word;
            }
            .user .bubble { background: #38b2ac; color: white; border-bottom-right-radius: 4px; }
            .agent .bubble { background: #edf2f7; color: #2d3748; border-bottom-left-radius: 4px; }
            #inputarea { 
                display: flex; 
                padding: 10px; 
                border-top: 1px solid #e2e8f0; 
                background: white; 
            }
            #userinput { 
                flex: 1; 
                padding: 10px; 
                font-size: 1rem; 
                border-radius: 6px; 
                border: 1px solid #cbd5e1; 
                margin-right: 8px; 
            }
            #sendbtn { 
                padding: 10px 18px; 
                font-size: 1rem; 
                border-radius: 6px; 
                border: none; 
                background: #38b2ac; 
                color: #fff; 
                cursor: pointer; 
                transition: background 0.2s; 
            }
            #sendbtn:hover { background: #2c7a7b; }
        </style>
    </head>
    <body>
        <div id="chatbox">
            <div id="chatlog"></div>
            <div id="inputarea">
                <input id="userinput" type="text" placeholder="Type your message..." />
                <button id="sendbtn"><i class="fa fa-paper-plane"></i></button>
            </div>
        </div>
        <script>
            const chatlog = document.getElementById('chatlog');
            const userinput = document.getElementById('userinput');
            const sendbtn = document.getElementById('sendbtn');
            
            sendbtn.onclick = sendMsg;
            userinput.addEventListener('keydown', function(e) { if (e.key === 'Enter') sendMsg(); });
            
            function addMessage(text, sender) {
                const msgDiv = document.createElement('div');
                msgDiv.classList.add('msg', sender);
                msgDiv.innerHTML = `<span class="bubble">${text}</span>`;
                chatlog.appendChild(msgDiv);
                chatlog.scrollTop = chatlog.scrollHeight;
            }
            
            function sendMsg() {
                const msg = userinput.value.trim();
                if (!msg) return;
                addMessage(msg, 'user');
                userinput.value = '';
                
                fetch('/chat', {
                     method: 'POST',
                     headers: { 'Content-Type': 'application/json' },
                     body: JSON.stringify({ question: msg })
                })
                .then(r => r.json())
                .then(data => {
                     addMessage(data.answer, 'agent');
                })
                .catch(() => {
                     addMessage("Error getting answer.", 'agent');
                });
            }
        </script>
    </body>
    </html>
    '''
    return html

@app.post('/chat')
async def chat_endpoint(request: Request):
    data = await request.json()
    question = data.get('question', '')
    # Load all articles
    articles = []
    if os.path.exists(SUMMARIES_DIR):
        for filename in sorted(os.listdir(SUMMARIES_DIR), reverse=True):
            if filename.endswith('.json'):
                with open(os.path.join(SUMMARIES_DIR, filename), 'r', encoding='utf-8') as f:
                    article = json.load(f)
                articles.append(article)
    # Select most relevant articles for the question
    relevant_articles = select_relevant_articles(question, articles, top_n=5)
    answer = get_llm_answer_together(question, relevant_articles)
    return JSONResponse({"answer": answer}) 