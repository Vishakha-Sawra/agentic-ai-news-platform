import os
import json
import re
from typing import List, Dict, Tuple
from sqlalchemy.orm import Session
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import Article, Category, ArticleCategory
from app.database import get_db, SessionLocal

class ContentCategorizer:
    """Service for automatically categorizing articles based on content"""
    
    def __init__(self):
        self.categories_cache = None
        self.stopwords = set(['the', 'is', 'at', 'which', 'on', 'a', 'an', 'and', 'or', 'for', 'to', 'of', 'in', 'with', 'by', 'as', 'from', 'that', 'this', 'it', 'are', 'be', 'was', 'were', 'has', 'had', 'have', 'but', 'not', 'if', 'then', 'so', 'do', 'does', 'did', 'can', 'will', 'just', 'about', 'into', 'over', 'after', 'before', 'more', 'less', 'than', 'up', 'out', 'off', 'no', 'yes', 'you', 'i', 'we', 'they', 'he', 'she', 'his', 'her', 'their', 'our', 'my', 'your'])
    
    def get_categories(self, db: Session) -> List[Category]:
        """Get all categories with their keywords"""
        if self.categories_cache is None:
            self.categories_cache = db.query(Category).all()
        return self.categories_cache
    
    def extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text"""
        # Convert to lowercase and extract words
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        # Remove stopwords
        keywords = [word for word in words if word not in self.stopwords]
        return keywords
    
    def calculate_relevance_score(self, article_text: str, category_keywords: List[str]) -> int:
        """Calculate relevance score (1-10) for an article to a category"""
        article_keywords = self.extract_keywords(article_text)
        article_text_lower = article_text.lower()
        
        score = 0
        matches = 0
        
        for keyword in category_keywords:
            keyword_lower = keyword.lower()
            # Check for exact keyword matches
            if keyword_lower in article_keywords:
                matches += 1
                score += 2
            # Check for keyword in title/summary (higher weight)
            elif keyword_lower in article_text_lower:
                matches += 1
                score += 1
        
        # Normalize score to 1-10 scale
        if matches == 0:
            return 0
        
        # Calculate score based on percentage of keywords matched and frequency
        keyword_match_ratio = matches / len(category_keywords) if category_keywords else 0
        normalized_score = min(10, max(1, int(score * keyword_match_ratio * 2)))
        
        return normalized_score
    
    def categorize_article(self, article_data: Dict, db: Session) -> List[Tuple[int, int]]:
        """
        Categorize a single article and return list of (category_id, relevance_score) tuples
        """
        categories = self.get_categories(db)
        article_text = f"{article_data.get('title', '')} {article_data.get('summary', '')} {article_data.get('llm_summary', '')}"
        
        categorizations = []
        
        for category in categories:
            if not category.keywords:
                continue
                
            relevance_score = self.calculate_relevance_score(article_text, category.keywords)
            
            # Only include categories with relevance score >= 3
            if relevance_score >= 3:
                categorizations.append((category.id, relevance_score))
        
        # Sort by relevance score (highest first)
        categorizations.sort(key=lambda x: x[1], reverse=True)
        
        # Return top 3 categories maximum
        return categorizations[:3]
    
    def sync_articles_from_files(self, summaries_dir: str = 'data/summaries/'):
        """Sync articles from JSON files to database and categorize them"""
        db = SessionLocal()
        try:
            if not os.path.exists(summaries_dir):
                print(f"Summaries directory not found: {summaries_dir}")
                return
            
            processed_count = 0
            categorized_count = 0
            
            for filename in os.listdir(summaries_dir):
                if not filename.endswith('.json'):
                    continue
                
                filepath = os.path.join(summaries_dir, filename)
                article_id = filename.replace('.json', '')
                
                # Check if article already exists
                existing_article = db.query(Article).filter(Article.id == article_id).first()
                if existing_article:
                    continue
                
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        article_data = json.load(f)
                    
                    # Create article record
                    article = Article(
                        id=article_id,
                        title=article_data.get('title', ''),
                        link=article_data.get('link', ''),
                        summary=article_data.get('summary', ''),
                        llm_summary=article_data.get('llm_summary', ''),
                        published=article_data.get('published', ''),
                        image_url=article_data.get('image_url', '')
                    )
                    db.add(article)
                    db.flush()  # Get the article ID
                    
                    # Categorize the article
                    categorizations = self.categorize_article(article_data, db)
                    
                    for category_id, relevance_score in categorizations:
                        article_category = ArticleCategory(
                            article_id=article_id,
                            category_id=category_id,
                            relevance_score=relevance_score
                        )
                        db.add(article_category)
                    
                    processed_count += 1
                    if categorizations:
                        categorized_count += 1
                    
                except Exception as e:
                    print(f"Error processing {filename}: {e}")
                    continue
            
            db.commit()
            print(f"Processed {processed_count} new articles, categorized {categorized_count}")
            
        except Exception as e:
            print(f"Error syncing articles: {e}")
            db.rollback()
        finally:
            db.close()
    
    def get_articles_by_category(self, db: Session, category_id: int, limit: int = 10) -> List[Article]:
        """Get articles for a specific category"""
        return (db.query(Article)
                .join(ArticleCategory)
                .filter(ArticleCategory.category_id == category_id)
                .order_by(ArticleCategory.relevance_score.desc(), Article.created_at.desc())
                .limit(limit)
                .all())
    
    def get_articles_by_keywords(self, db: Session, keywords: List[str], limit: int = 10) -> List[Article]:
        """Get articles that match specific keywords"""
        if not keywords:
            return []
        
        # Create a search pattern
        search_terms = [f"%{keyword.lower()}%" for keyword in keywords]
        
        articles = []
        for term in search_terms:
            matching_articles = (db.query(Article)
                               .filter(
                                   (Article.title.ilike(term)) |
                                   (Article.summary.ilike(term)) |
                                   (Article.llm_summary.ilike(term))
                               )
                               .order_by(Article.created_at.desc())
                               .limit(limit)
                               .all())
            articles.extend(matching_articles)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_articles = []
        for article in articles:
            if article.id not in seen:
                seen.add(article.id)
                unique_articles.append(article)
        
        return unique_articles[:limit]

# Global instance
categorizer = ContentCategorizer()

def categorize_new_article(article_data: Dict) -> List[Tuple[int, int]]:
    """Categorize a newly scraped article"""
    db = SessionLocal()
    try:
        return categorizer.categorize_article(article_data, db)
    finally:
        db.close()

def sync_articles():
    """Sync articles from files to database"""
    categorizer.sync_articles_from_files()

if __name__ == "__main__":
    sync_articles()