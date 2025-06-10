"""
Memory Manager for the Philosophical Multi-Agent Debate System.
Handles persistent storage and retrieval of agent memories and debate history.
"""

import os
import json
import datetime
from typing import Dict, List, Any, Optional, Tuple, Union
from pathlib import Path


class MemoryManager:
    """
    Manages persistent memory for the debate system, including:
    - Agent-specific memories (past positions, evolving viewpoints)
    - Debate history (prompts, responses, critiques, summaries)
    - Cross-references between related debates
    """
    
    def __init__(self, memory_dir: Optional[str] = None):
        """
        Initialize the MemoryManager with a directory for storing memory files.
        
        Args:
            memory_dir: Directory path for storing memory files. If None,
                       defaults to {project_root}/memory/
        """
        if memory_dir is None:
            # Default to {project_root}/memory/
            project_root = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            self.memory_dir = project_root / "memory"
        else:
            self.memory_dir = Path(memory_dir)
            
        # Create memory directory structure if it doesn't exist
        self._ensure_memory_dirs()
        
        # Cache for in-memory storage of frequently accessed data
        self.cache = {
            "agent_memories": {},      # Indexed by agent name
            "debate_history": [],      # List of debate entries
            "topic_index": {}          # Topic -> list of debate IDs
        }
        
        # Load existing memory files into cache
        self._initialize_cache()
    
    def _ensure_memory_dirs(self) -> None:
        """
        Create the necessary directory structure for memory storage.
        """
        os.makedirs(self.memory_dir, exist_ok=True)
        os.makedirs(self.memory_dir / "agents", exist_ok=True)
        os.makedirs(self.memory_dir / "debates", exist_ok=True)
        os.makedirs(self.memory_dir / "indexes", exist_ok=True)
    
    def _initialize_cache(self) -> None:
        """
        Load existing memory files into cache for faster access.
        """
        # Load agent memories
        agent_dir = self.memory_dir / "agents"
        if agent_dir.exists():
            for agent_file in agent_dir.glob("*.json"):
                try:
                    with open(agent_file, 'r') as f:
                        agent_name = agent_file.stem  # Filename without extension
                        self.cache["agent_memories"][agent_name] = json.load(f)
                except Exception as e:
                    print(f"Error loading agent memory {agent_file}: {e}")
        
        # Load debate history index
        debate_index_path = self.memory_dir / "indexes" / "debate_index.json"
        if debate_index_path.exists():
            try:
                with open(debate_index_path, 'r') as f:
                    self.cache["debate_history"] = json.load(f)
            except Exception as e:
                print(f"Error loading debate index: {e}")
        
        # Load topic index
        topic_index_path = self.memory_dir / "indexes" / "topic_index.json"
        if topic_index_path.exists():
            try:
                with open(topic_index_path, 'r') as f:
                    self.cache["topic_index"] = json.load(f)
            except Exception as e:
                print(f"Error loading topic index: {e}")
    
    def save_debate(self, debate_data: Dict[str, Any]) -> str:
        """
        Save a complete debate record and update related indexes.
        
        Args:
            debate_data: Dictionary containing debate information including:
                        - prompt: The original philosophical prompt
                        - responses: List of agent responses
                        - critiques: List of critiques between agents
                        - summary: Final debate summary
                        
        Returns:
            debate_id: Unique identifier for the saved debate
        """
        # Generate a unique debate ID based on timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        debate_id = f"debate_{timestamp}"
        
        # Add metadata
        debate_data["debate_id"] = debate_id
        debate_data["timestamp"] = timestamp
        
        # Extract topics and create a more user-friendly date
        topic_keywords = self._extract_topics(debate_data["prompt"])
        debate_data["topics"] = topic_keywords
        
        # Add a formatted date (for better UI display)
        formatted_date = datetime.datetime.now().strftime("%B %d, %Y")
        debate_data["date"] = formatted_date
        
        # Extract main topic from prompt (first sentence or until first period)
        prompt = debate_data.get("prompt", "")
        main_topic = prompt.split(".")[0] if prompt else "Unknown"
        if len(main_topic) > 50:  # Truncate if too long
            main_topic = main_topic[:47] + "..."
        debate_data["topic"] = main_topic
        
        # Save the complete debate record
        debate_path = self.memory_dir / "debates" / f"{debate_id}.json"
        with open(debate_path, 'w') as f:
            json.dump(debate_data, f, indent=2)
        
        # Update debate index
        index_entry = {
            "debate_id": debate_id,
            "id": debate_id,  # For compatibility with explorer
            "timestamp": timestamp,
            "date": debate_data["date"],
            "prompt": debate_data["prompt"],
            "topic": debate_data["topic"],
            "topics": debate_data["topics"],
            "agent_count": len(debate_data.get("responses", [])),
            "agents": [resp.get("agent", "Unknown") for resp in debate_data.get("responses", [])],
            "file_path": str(debate_path)
        }
        
        self.cache["debate_history"].append(index_entry)
        self._save_debate_index()
        
        # Update topic index
        for topic in debate_data["topics"]:
            if topic not in self.cache["topic_index"]:
                self.cache["topic_index"][topic] = []
            self.cache["topic_index"][topic].append(debate_id)
        self._save_topic_index()
        
        # Update individual agent memories
        self._update_agent_memories(debate_data)
        
        return debate_id
    
    def _extract_topics(self, prompt: str) -> List[str]:
        """
        Extract key topics from a debate prompt for indexing.
        
        Args:
            prompt: The debate prompt string
            
        Returns:
            List of extracted topics
        """
        # This is a simple implementation - in a production system,
        # consider using NLP techniques like keyword extraction
        words = prompt.lower().split()
        stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "by"}
        topics = [w for w in words if len(w) > 3 and w not in stopwords]
        
        # Deduplicate and take most significant
        return sorted(set(topics))[:5]
    
    def _update_agent_memories(self, debate_data: Dict[str, Any]) -> None:
        """
        Update memories for individual agents based on their participation in a debate.
        
        Args:
            debate_data: Complete debate data including agent responses and critiques
        """
        if "responses" not in debate_data:
            return
            
        for agent_response in debate_data["responses"]:
            agent_name = agent_response.get("agent", "Unknown")
            response_text = agent_response.get("response", "")
            
            # If agent name is missing, try to extract it from the response
            if agent_name == "Unknown" and response_text:
                # Try to find signatures like "- The Utilitarian" or "Sincerely, Kantian"
                signature_patterns = [
                    r'- The ([A-Za-z]+)',
                    r'--([A-Za-z]+)',
                    r'Sincerely, ([A-Za-z]+)',
                    r'([A-Za-z]+) Perspective:'
                ]
                
                for pattern in signature_patterns:
                    import re
                    match = re.search(pattern, response_text)
                    if match:
                        extracted_name = match.group(1).strip()
                        if len(extracted_name) > 2:  # Avoid things like "I" or "A"
                            agent_name = extracted_name
                            # Update the original response data
                            agent_response["agent"] = agent_name
                            break
            
            # Initialize agent memory if not exists
            if agent_name not in self.cache["agent_memories"]:
                self.cache["agent_memories"][agent_name] = {
                    "name": agent_name,
                    "debates": [],
                    "positions": {},  # Store positions indexed by topic
                    "topics_addressed": []
                }
            
            # Update agent's debate participation
            debate_entry = {
                "debate_id": debate_data["debate_id"],
                "topic": debate_data.get("topic", "Unknown"),
                "prompt": debate_data["prompt"],
                "response": response_text,
                "timestamp": debate_data["timestamp"],
                "date": debate_data.get("date", "Unknown")
            }
            
            self.cache["agent_memories"][agent_name]["debates"].append(debate_entry)
            
            # Update topics this agent has addressed
            main_topic = debate_data.get("topic", "Unknown")
            if main_topic != "Unknown":
                if main_topic not in self.cache["agent_memories"][agent_name]["topics_addressed"]:
                    self.cache["agent_memories"][agent_name]["topics_addressed"].append(main_topic)
            
            # Store position on this topic
            if main_topic != "Unknown":
                if main_topic not in self.cache["agent_memories"][agent_name]["positions"]:
                    self.cache["agent_memories"][agent_name]["positions"][main_topic] = []
                
                position_entry = {
                    "debate_id": debate_data["debate_id"],
                    "date": debate_data.get("date", "Unknown"),
                    "timestamp": debate_data["timestamp"],
                    "position": response_text[:500] + ("..." if len(response_text) > 500 else "")  # Truncate for storage
                }
                
                self.cache["agent_memories"][agent_name]["positions"][main_topic].append(position_entry)
            
            # Also update positions for keyword topics
            for topic in debate_data.get("topics", []):
                if topic not in self.cache["agent_memories"][agent_name]["topics_addressed"]:
                    self.cache["agent_memories"][agent_name]["topics_addressed"].append(topic)
            
            # Save updated agent memory
            self._save_agent_memory(agent_name)
    
    def _save_debate_index(self) -> None:
        """
        Save the debate history index to disk.
        """
        index_path = self.memory_dir / "indexes" / "debate_index.json"
        with open(index_path, 'w') as f:
            json.dump(self.cache["debate_history"], f, indent=2)
    
    def _save_topic_index(self) -> None:
        """
        Save the topic index to disk.
        """
        index_path = self.memory_dir / "indexes" / "topic_index.json"
        with open(index_path, 'w') as f:
            json.dump(self.cache["topic_index"], f, indent=2)
    
    def _save_agent_memory(self, agent_name: str) -> None:
        """
        Save an individual agent's memory to disk.
        
        Args:
            agent_name: Name of the agent whose memory to save
        """
        if agent_name not in self.cache["agent_memories"]:
            return
            
        agent_path = self.memory_dir / "agents" / f"{agent_name}.json"
        with open(agent_path, 'w') as f:
            json.dump(self.cache["agent_memories"][agent_name], f, indent=2)
    
    def get_agent_memory(self, agent_name: str) -> Dict[str, Any]:
        """
        Retrieve an agent's complete memory.
        
        Args:
            agent_name: Name of the agent to retrieve memory for
            
        Returns:
            Dictionary containing agent's memory
        """
        return self.cache["agent_memories"].get(agent_name, {"name": agent_name, "debates": []})
    
    def get_relevant_debates(self, prompt: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Find debates that are relevant to a given prompt.
        
        Args:
            prompt: The current debate prompt
            limit: Maximum number of relevant debates to return
            
        Returns:
            List of relevant debate data
        """
        topics = self._extract_topics(prompt)
        relevant_debates = []
        debate_scores = {}
        
        # Find debates with overlapping topics
        for topic in topics:
            if topic in self.cache["topic_index"]:
                for debate_id in self.cache["topic_index"][topic]:
                    if debate_id not in debate_scores:
                        debate_scores[debate_id] = 0
                    debate_scores[debate_id] += 1
        
        # Sort debates by relevance score
        sorted_debates = sorted(debate_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Load full debate data for top matches
        for debate_id, score in sorted_debates[:limit]:
            for debate_entry in self.cache["debate_history"]:
                if debate_entry["debate_id"] == debate_id:
                    # Load full debate data
                    debate_path = Path(debate_entry["file_path"])
                    try:
                        with open(debate_path, 'r') as f:
                            relevant_debates.append(json.load(f))
                    except Exception as e:
                        print(f"Error loading debate {debate_id}: {e}")
        
        return relevant_debates
    
    def get_agent_position(self, agent_name: str, topic: str) -> Optional[str]:
        """
        Get an agent's position on a specific topic based on past debates.
        
        Args:
            agent_name: Name of the agent
            topic: Topic to find position on
            
        Returns:
            Agent's position on the topic, or None if no position found
        """
        agent_memory = self.get_agent_memory(agent_name)
        
        # Find debates where this agent addressed this topic
        relevant_debates = []
        for debate in agent_memory.get("debates", []):
            debate_data_path = self.memory_dir / "debates" / f"{debate['debate_id']}.json"
            try:
                with open(debate_data_path, 'r') as f:
                    debate_data = json.load(f)
                    if topic in debate_data.get("topics", []):
                        relevant_debates.append(debate)
            except Exception:
                pass
        
        # No relevant debates found
        if not relevant_debates:
            return None
            
        # Return most recent position on this topic
        relevant_debates.sort(key=lambda x: x["timestamp"], reverse=True)
        return relevant_debates[0]["response"]
    
    def get_debate_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get a list of past debates.
        
        Args:
            limit: Maximum number of debates to return
            
        Returns:
            List of debate summary entries
        """
        # Sort by timestamp (newest first)
        sorted_history = sorted(
            self.cache["debate_history"], 
            key=lambda x: x["timestamp"], 
            reverse=True
        )
        
        return sorted_history[:limit]
