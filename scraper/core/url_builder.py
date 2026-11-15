"""URL Builder for LinkedIn job searches"""

from urllib.parse import quote_plus
from config.settings import (
    LINKEDIN_BASE_URL, LINKEDIN_SEE_MORE_URL, TIME_POSTED_MAPPING, EXPERIENCE_LEVELS)


class LinkedInURLBuilder:
    """Builds LinkedIn search URLs from search configuration"""
    
    @staticmethod
    def build_url(search_config):
        """Convert SearchConfig to LinkedIn URL"""
        query_params = LinkedInURLBuilder._query_params(search_config)

        # Build final URL
        if query_params:
            final_url = f"{LINKEDIN_BASE_URL}?{'&'.join(query_params)}"
            print(f"🔗 Generated URL: {final_url}")
            return final_url
        else:
            return LINKEDIN_BASE_URL

    @staticmethod
    def build_see_more_url(search_config, start):
        """URL of the next result page ("See more jobs"), after `start` cards."""
        query_params = LinkedInURLBuilder._query_params(search_config, verbose=False)
        query_params.append(f"start={int(start)}")
        return f"{LINKEDIN_SEE_MORE_URL}?{'&'.join(query_params)}"

    @staticmethod
    def _query_params(search_config, verbose=True):
        """Search query parameters shared by the search page and see-more URLs."""
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
                    if verbose:
                        print(f"⚠️  Warning: Invalid experience level {level}, skipping")
            
            if valid_levels:
                # Join multiple levels with commas and URL encode
                experience_param = ','.join(valid_levels)
                encoded_experience = quote_plus(experience_param)
                query_params.append(f"f_E={encoded_experience}")
                
                # Debug info
                if verbose:
                    level_names = [EXPERIENCE_LEVELS.get(int(level), f"Level {level}") for level in valid_levels]
                    print(f"🎯 Experience filter: {', '.join(level_names)} (codes: {experience_param})")
        
        # Remote work
        if search_config.remote:
            query_params.append("f_WT=2")
            if verbose:
                print(f"🏠 Remote filter: enabled")

        return query_params