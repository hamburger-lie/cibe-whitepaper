import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional


DEFAULT_REFLECTION_STORAGE_PATH = os.path.join("data", "reflections.json")


class ReflectionStorage:
    """
    A class for storing and retrieving user reflections with timestamps.
    """
    
    def __init__(self, storage_path: str = DEFAULT_REFLECTION_STORAGE_PATH):
        """
        Initialize the ReflectionStorage with a storage file path.
        
        Args:
            storage_path: Path to the JSON file for storing reflections
        """
        self.storage_path = storage_path
        self._ensure_storage_file_exists()
    
    def _ensure_storage_file_exists(self) -> None:
        """Ensure the storage file exists, create it if it doesn't."""
        storage_dir = os.path.dirname(self.storage_path)
        if storage_dir:
            os.makedirs(storage_dir, exist_ok=True)
        if not os.path.exists(self.storage_path):
            with open(self.storage_path, 'w') as f:
                json.dump([], f)
                f.flush()  # Ensure the data is written to disk
                os.fsync(f.fileno())  # Force write to disk
        else:
            # Check if file is empty and initialize if needed
            try:
                with open(self.storage_path, 'r') as f:
                    content = f.read().strip()
                    if not content:
                        # File is empty, initialize it
                        with open(self.storage_path, 'w') as f:
                            json.dump([], f)
                            f.flush()
                            os.fsync(f.fileno())
            except Exception:
                # If we can't read the file, recreate it
                with open(self.storage_path, 'w') as f:
                    json.dump([], f)
                    f.flush()
                    os.fsync(f.fileno())
    
    def save_reflection(self, reflection: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Save a reflection to the storage.
        
        Args:
            reflection: The reflection text to save
            metadata: Optional metadata dictionary to store with the reflection
            
        Returns:
            bool: True if reflection was saved successfully, False otherwise
        """
        if not reflection or not reflection.strip():
            return False
        
        try:
            # Load existing reflections
            try:
                with open(self.storage_path, 'r') as f:
                    content = f.read().strip()
                    if not content:
                        reflections = []
                    else:
                        reflections = json.loads(content)
            except (json.JSONDecodeError, IOError):
                # If file is corrupted or empty, start fresh
                reflections = []
            
            # Create new reflection entry
            new_reflection = {
                "id": len(reflections) + 1,
                "text": reflection.strip(),
                "timestamp": datetime.now().isoformat(),
                "metadata": metadata or {}
            }
            
            # Add to reflections list
            reflections.append(new_reflection)
            
            # Save back to file
            with open(self.storage_path, 'w') as f:
                json.dump(reflections, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            
            return True
            
        except Exception as e:
            print(f"Error saving reflection: {e}")
            return False
    
    def get_reflections(self, limit: Optional[int] = None, 
                       start_date: Optional[str] = None, 
                       end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get stored reflections with optional filtering.
        
        Args:
            limit: Maximum number of reflections to return (most recent first)
            start_date: Filter reflections from this date (ISO format)
            end_date: Filter reflections up to this date (ISO format)
            
        Returns:
            List of reflection dictionaries
        """
        try:
            with open(self.storage_path, 'r') as f:
                content = f.read().strip()
                if not content:
                    return []
                reflections = json.loads(content)
        except (IOError, json.JSONDecodeError) as e:
            print(f"Error loading reflections: {e}")
            return []
        
        # Sort by timestamp (most recent first)
        reflections.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Apply date filters if provided
        if start_date or end_date:
            filtered_reflections = []
            for reflection in reflections:
                timestamp = reflection.get('timestamp', '')
                if start_date and timestamp < start_date:
                    continue
                if end_date and timestamp > end_date:
                    continue
                filtered_reflections.append(reflection)
            reflections = filtered_reflections
        
        # Apply limit if provided
        if limit is not None and limit > 0:
            reflections = reflections[:limit]
        
        return reflections
    
    def get_reflection_by_id(self, reflection_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific reflection by its ID.
        
        Args:
            reflection_id: The ID of the reflection to retrieve
            
        Returns:
            Reflection dictionary or None if not found
        """
        reflections = self.get_reflections()
        for reflection in reflections:
            if reflection.get('id') == reflection_id:
                return reflection
        return None
    
    def delete_reflection(self, reflection_id: int) -> bool:
        """
        Delete a reflection by its ID.
        
        Args:
            reflection_id: The ID of the reflection to delete
            
        Returns:
            bool: True if reflection was deleted, False if not found or error
        """
        try:
            with open(self.storage_path, 'r') as f:
                reflections = json.load(f)
            
            # Find and remove the reflection
            original_length = len(reflections)
            reflections = [r for r in reflections if r.get('id') != reflection_id]
            
            if len(reflections) == original_length:
                return False  # Reflection not found
            
            # Save back to file
            with open(self.storage_path, 'w') as f:
                json.dump(reflections, f, indent=2)
            
            return True
            
        except (IOError, json.JSONDecodeError) as e:
            print(f"Error deleting reflection: {e}")
            return False
    
    def get_reflection_history(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get reflection history with pagination support.
        
        Args:
            limit: Maximum number of reflections to return
            offset: Offset for pagination
            
        Returns:
            List of reflection records
        """
        reflections = self.get_reflections(limit=limit + offset)
        return reflections[offset:offset + limit]
    
    def get_reflections_by_type(self, reflection_type: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get reflections by type.
        
        Args:
            reflection_type: Type of reflections to retrieve
            limit: Maximum number of reflections to return
            
        Returns:
            List of reflection records of the specified type
        """
        reflections = self.get_reflections()
        filtered_reflections = [
            r for r in reflections 
            if r.get('metadata', {}).get('type') == reflection_type
        ][:limit]
        return filtered_reflections
    
    def get_reflection(self, reflection_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific reflection by ID (string version).
        
        Args:
            reflection_id: ID of the reflection to retrieve
            
        Returns:
            Reflection record or None if not found
        """
        try:
            reflection_id_int = int(reflection_id)
            return self.get_reflection_by_id(reflection_id_int)
        except ValueError:
            return None
