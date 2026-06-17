import logging
from neo4j import AsyncGraphDatabase, AsyncDriver
from app.config import settings
from typing import Optional

logger = logging.getLogger(__name__)

class Neo4jEngine:
    def __init__(self):
        self.uri = settings.NEO4J_URI
        self.user = settings.NEO4J_USER
        self.password = settings.NEO4J_PASSWORD
        self.driver: Optional[AsyncDriver] = None

    async def connect(self):
        try:
            self.driver = AsyncGraphDatabase.driver(
                self.uri, auth=(self.user, self.password)
            )
            # Verify connection
            await self.driver.verify_connectivity()
            logger.info("Successfully connected to Neo4j")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {str(e)}")
            raise

    async def close(self):
        if self.driver:
            await self.driver.close()
            logger.info("Neo4j connection closed")

    async def initialize_constraints(self):
        """Initialize database constraints and indexes"""
        if not self.driver:
            return

        queries = [
            "CREATE CONSTRAINT coach_id IF NOT EXISTS FOR (c:Coach) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT client_id IF NOT EXISTS FOR (c:Client) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT lead_id IF NOT EXISTS FOR (l:Lead) REQUIRE l.id IS UNIQUE",
            "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (e:Event) REQUIRE e.id IS UNIQUE",
        ]
        
        async with self.driver.session() as session:
            for query in queries:
                try:
                    await session.run(query)
                except Exception as e:
                    logger.warning(f"Error executing constraint: {str(e)}")

# Global instance
neo4j_engine = Neo4jEngine()
