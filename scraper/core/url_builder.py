"""URL Builder for LinkedIn job searches"""

import requests
from urllib.parse import quote_plus
from config.settings import LINKEDIN_BASE_URL, TIME_POSTED_MAPPING, EXPERIENCE_LEVELS


class LinkedInURLBuilder:
    """Builds LinkedIn search URLs from search configuration"""
    
    @staticmethod
    def build_url(search_config):
        """Convert SearchConfig to LinkedIn URL"""
        query_params = []
        
        # Keywords - handle multiple words properly
        if search_config.keywords:
            keywords = search_config.keywords.strip()
            # Use quote_plus to properly encode spaces and special characters
            encoded_keywords = quote_plus(keywords)
            query_params.append(f"keywords={encoded_keywords}")
        
        # Location
        if search_config.location:
            location = search_config.location.strip()
            encoded_location = quote_plus(location)
            query_params.append(f"location={encoded_location}")
        
        # Time Posted
        if search_config.time_posted and search_config.time_posted in TIME_POSTED_MAPPING:
            time_code = TIME_POSTED_MAPPING[search_config.time_posted]
            query_params.append(f"f_TPR=r{time_code}")
        
        # Experience Levels (NEW)
        if search_config.experience_levels:
            # Validate experience levels
            valid_levels = []
            for level in search_config.experience_levels:
                if isinstance(level, int) and 1 <= level <= 6:
                    valid_levels.append(str(level))
                else:
                    print(f"⚠️  Warning: Invalid experience level {level}, skipping")
            
            if valid_levels:
                # Join multiple levels with commas and URL encode
                experience_param = ','.join(valid_levels)
                encoded_experience = quote_plus(experience_param)
                query_params.append(f"f_E={encoded_experience}")
                
                # Debug info
                level_names = [EXPERIENCE_LEVELS.get(int(level), f"Level {level}") for level in valid_levels]
                print(f"🎯 Experience filter: {', '.join(level_names)} (codes: {experience_param})")
        
        # Remote work
        if search_config.remote:
            query_params.append("f_WT=2")
            print(f"🏠 Remote filter: enabled")
        
        # Build final URL
        if query_params:
            final_url = f"{LINKEDIN_BASE_URL}?{'&'.join(query_params)}"
            print(f"🔗 Generated URL: {final_url}")
            return final_url
        else:
            return LINKEDIN_BASE_URL
    
    @staticmethod
    def get_experience_level_info():
        """Get human-readable experience level information"""
        print("📊 Available Experience Levels:")
        for code, name in EXPERIENCE_LEVELS.items():
            print(f"   {code}: {name}")
        print()
        print("💡 Usage examples:")
        print("   experience_levels=[2]      # Entry level only")
        print("   experience_levels=[2,3]    # Entry + Associate")
        print("   experience_levels=[1,2,3]  # All junior levels")
        print("   experience_levels=[4,5,6]  # All senior levels")