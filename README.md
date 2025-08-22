# 🚀 Tech News Digest - Personalized AI-Powered News Aggregation

A sophisticated tech news aggregation platform that delivers personalized daily and weekly digests using AI-powered content categorization and email notifications.

## ✨ Features

### 🔔 **Personalized Digests & Notifications**
- **Daily Digests**: Personalized morning summaries of tech news
- **Weekly Roundups**: Comprehensive weekly reports with trending topics
- **Instant Notifications**: Breaking news alerts for high-impact stories
- **Smart Categorization**: AI-powered content classification into 10 tech categories
- **Custom Keywords**: Subscribe to specific topics with custom keyword filters

### 🤖 **AI-Powered Intelligence**
- **Content Categorization**: Automatic article classification using keyword matching and relevance scoring
- **Smart Summaries**: AI-generated article summaries using Together AI
- **Personalization Engine**: Content recommendation based on user interests
- **Interactive Chat**: Ask questions about recent tech news with AI assistant

### 👥 **User Management**
- **User Authentication**: JWT-based secure authentication
- **Preference Management**: Customizable digest frequency and topics
- **Subscription Control**: Granular control over notification types
- **Usage Analytics**: Track digest history and engagement

## 🏗️ Architecture

```
├── webapp.py              # Main FastAPI application with web UI and API
├── models.py              # SQLAlchemy database models
├── database.py            # Database configuration and initialization
├── auth.py                # JWT authentication and user management
├── schemas.py             # Pydantic models for API validation
├── scheduler_service.py   # APScheduler for automated digest sending
├── services/
│   ├── categorization_service.py  # AI content categorization
│   ├── digest_service.py          # Digest generation and sending
│   └── email_service.py           # Email templates and SMTP
├── scrapers/
│   └── techcrunch.py      # News scraping and processing
└── data/summaries/        # Processed article storage
```

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone <repository-url>
cd tech-news-digest

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Setup

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your configuration
nano .env
```

Required environment variables:
- `TOGETHER_API_KEY`: For AI summaries and chat
- `SMTP_*`: Email configuration for digest delivery
- `SECRET_KEY`: JWT token encryption (generate a secure key)

### 3. Database Initialization

```bash
# Initialize database and create default categories
python database.py
```

### 4. Start the Application

```bash
# Start the web application
uvicorn webapp:app --reload --host 0.0.0.0 --port 8000
```

### 5. Start the Scheduler (Optional)

```bash
# Start automated digest scheduler in a separate terminal
python scheduler_service.py
```

## 📖 Usage

### Web Interface

Visit `http://localhost:8000` to access the web interface where you can:
- Browse categorized tech news articles
- Subscribe to personalized digests
- Chat with the AI assistant about recent news

### API Documentation

Interactive API documentation is available at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Key API Endpoints

#### Authentication
```bash
# Register a new user
POST /auth/register
{
  "email": "user@example.com",
  "password": "securepassword",
  "full_name": "John Doe"
}

# Login and get access token
POST /auth/token
username=user@example.com&password=securepassword
```

#### Preferences Management
```bash
# Get user preferences
GET /preferences
Authorization: Bearer <token>

# Update digest preferences
PUT /preferences
Authorization: Bearer <token>
{
  "daily_digest_enabled": true,
  "weekly_digest_enabled": true,
  "instant_notifications": false,
  "digest_time": "09:00",
  "interested_categories": [1, 2, 3]
}
```

#### Digest Operations
```bash
# Preview personalized digest
GET /digest/preview?digest_type=daily
Authorization: Bearer <token>

# Send digest immediately
POST /digest/send?digest_type=daily
Authorization: Bearer <token>

# Get digest history
GET /digest/history
Authorization: Bearer <token>
```

#### Content Access
```bash
# Get all articles
GET /articles?category_id=1&limit=20

# Get personalized articles
GET /articles/personalized?limit=20
Authorization: Bearer <token>

# Get available categories
GET /categories
```

## 🎯 Content Categories

The system automatically categorizes articles into these domains:

1. **🤖 Artificial Intelligence** - AI, ML, automation, neural networks
2. **💰 Startups & Funding** - Venture capital, funding rounds, IPOs
3. **🏢 Big Tech** - Google, Apple, Microsoft, Amazon, Meta news
4. **🔒 Cybersecurity** - Security breaches, privacy, data protection
5. **📱 Mobile & Apps** - Smartphones, mobile apps, tablets
6. **🏭 Enterprise & SaaS** - Business software, productivity tools
7. **🎮 Gaming** - Video games, esports, gaming platforms
8. **🚗 Electric Vehicles** - EVs, autonomous driving, transportation
9. **💳 Fintech** - Cryptocurrency, digital payments, blockchain
10. **📱 Social Media** - Social platforms, creator economy

## ⚙️ Configuration

### Digest Scheduling

Default schedule (configurable in `scheduler_service.py`):
- **Daily Digests**: 9:00 AM every day
- **Weekly Digests**: Monday 9:00 AM
- **Article Sync**: Every hour

### Email Templates

Professional HTML email templates with:
- Responsive design for mobile and desktop
- Category-based organization
- Personalized content based on user interests
- Unsubscribe and preference management links

### Categorization Algorithm

The AI categorization system:
1. Extracts keywords from article title, summary, and AI summary
2. Matches against predefined category keywords
3. Calculates relevance scores (1-10 scale)
4. Assigns articles to top 3 matching categories
5. Only includes categories with relevance score ≥ 3

## 🔧 Advanced Features

### Custom Keyword Subscriptions

Users can create custom subscriptions with specific keywords:

```bash
POST /subscriptions
Authorization: Bearer <token>
{
  "subscription_type": "daily",
  "keywords": ["quantum computing", "machine learning", "startup funding"]
}
```

### Instant Notifications

High-impact articles (relevance score ≥ 7) trigger instant notifications to subscribed users.

### Content Personalization

The system personalizes content by:
- User-selected category interests
- Custom keyword subscriptions
- Historical engagement patterns
- Relevance scoring algorithms

## 📊 Benefits

### For Users
- **Time-Saving**: Curated, personalized content delivery
- **Comprehensive Coverage**: Never miss important tech news
- **Smart Filtering**: Focus on topics that matter to you
- **Flexible Delivery**: Choose your preferred digest frequency

### For Organizations
- **Employee Engagement**: Keep teams informed about industry trends
- **Market Intelligence**: Track competitor and industry developments
- **Knowledge Sharing**: Centralized tech news for research teams
- **Customizable**: Adapt to specific organizational interests

## 🚀 Production Deployment

### Environment Variables
```bash
# Production settings
SECRET_KEY=your_production_secret_key
DATABASE_URL=postgresql://user:pass@host:port/dbname
SMTP_SERVER=your_production_smtp_server
```

### Docker Deployment
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "webapp:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Monitoring
- API endpoint health checks
- Email delivery monitoring
- User engagement analytics
- System performance metrics
