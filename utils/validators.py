"""Input validation utilities"""

def validate_search_config(config):
    """Validate search configuration parameters"""
    if not isinstance(config, dict):
        raise ValueError("Search config must be a dictionary")
    
    # Validate keywords
    if 'keywords' in config:
        if not isinstance(config['keywords'], str) or not config['keywords'].strip():
            raise ValueError("Keywords must be a non-empty string")
    
    # Validate location
    if 'location' in config:
        if not isinstance(config['location'], str) or not config['location'].strip():
            raise ValueError("Location must be a non-empty string")
    
    # Validate time_posted
    if 'time_posted' in config:
        valid_times = ['24h', '1w', '1m']
        if config['time_posted'] not in valid_times:
            raise ValueError(f"time_posted must be one of: {valid_times}")
    
    # Validate remote
    if 'remote' in config:
        if not isinstance(config['remote'], bool):
            raise ValueError("remote must be a boolean value")
    
    return True