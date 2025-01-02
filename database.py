import aiosqlite
import logging
import os

class Database:
    def __init__(self, db_name: str = "referral_bot.db"):
        self.db_name = db_name
        # Ensure the database directory exists and is writable
        db_dir = os.path.dirname(os.path.abspath(db_name))
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    async def init_db(self):
        try:
            self.logger.info(f"Initializing database at {os.path.abspath(self.db_name)}")
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        telegram_id INTEGER PRIMARY KEY,
                        inviter_id INTEGER,
                        referrals INTEGER DEFAULT 0,
                        is_member BOOLEAN DEFAULT TRUE,
                        has_chatted BOOLEAN DEFAULT FALSE,
                        join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (inviter_id) REFERENCES users(telegram_id)
                    )
                ''')
                
                # Add has_chatted column to existing table if it doesn't exist
                try:
                    await db.execute('ALTER TABLE users ADD COLUMN has_chatted BOOLEAN DEFAULT FALSE')
                    self.logger.info("Added has_chatted column to users table")
                except:
                    self.logger.info("has_chatted column already exists")
                
                await db.commit()
                self.logger.info("Database initialized successfully")
                
                # Verify table exists
                async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'") as cursor:
                    if not await cursor.fetchone():
                        raise Exception("Failed to create users table")
                        
        except Exception as e:
            self.logger.error(f"Error initializing database: {e}", exc_info=True)
            raise

    async def get_inviter(self, telegram_id: int) -> int:
        """Get the inviter ID for a user"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                async with db.execute(
                    'SELECT inviter_id FROM users WHERE telegram_id = ?',
                    (telegram_id,)
                ) as cursor:
                    result = await cursor.fetchone()
                    return result[0] if result else None
        except Exception as e:
            self.logger.error(f"Error getting inviter: {e}")
            return None

    async def add_user(self, telegram_id: int, inviter_id: int = None) -> bool:
        """Add or update a user in the database"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                # Check if user exists
                async with db.execute(
                    'SELECT telegram_id, inviter_id, is_member FROM users WHERE telegram_id = ?',
                    (telegram_id,)
                ) as cursor:
                    existing_user = await cursor.fetchone()

                if existing_user:
                    # User exists but was not a member
                    if not existing_user[2]:  # if not is_member
                        await db.execute(
                            'UPDATE users SET is_member = TRUE WHERE telegram_id = ?',
                            (telegram_id,)
                        )
                        if inviter_id:
                            # Update inviter's referral count
                            await db.execute(
                                'UPDATE users SET referrals = referrals + 1 WHERE telegram_id = ?',
                                (inviter_id,)
                            )
                            self.logger.info(f"Updated referral count for inviter {inviter_id}")
                        await db.commit()
                        return True
                    return False
                
                # Add new user
                await db.execute(
                    'INSERT INTO users (telegram_id, inviter_id, is_member, has_chatted) VALUES (?, ?, TRUE, FALSE)',
                    (telegram_id, inviter_id)
                )
                
                # Update inviter's referral count
                if inviter_id:
                    await db.execute(
                        'UPDATE users SET referrals = referrals + 1 WHERE telegram_id = ?',
                        (inviter_id,)
                    )
                    self.logger.info(f"Incremented referral count for inviter {inviter_id}")
                
                await db.commit()
                return True
                
        except Exception as e:
            self.logger.error(f"Error adding user: {e}", exc_info=True)
            return False

    async def remove_user(self, telegram_id: int) -> bool:
        """Mark a user as not a member and update referral counts"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                # Get user's current status and inviter
                async with db.execute(
                    'SELECT is_member, inviter_id FROM users WHERE telegram_id = ?',
                    (telegram_id,)
                ) as cursor:
                    user_data = await cursor.fetchone()
                    
                    if not user_data:
                        return False
                    
                    is_member, inviter_id = user_data
                    
                    if not is_member:  # Already marked as not a member
                        return False

                # Update user's member status
                await db.execute(
                    'UPDATE users SET is_member = FALSE WHERE telegram_id = ?',
                    (telegram_id,)
                )
                
                # Decrease inviter's referral count if exists
                if inviter_id:
                    await db.execute(
                        'UPDATE users SET referrals = CASE WHEN referrals > 0 THEN referrals - 1 ELSE 0 END WHERE telegram_id = ?',
                        (inviter_id,)
                    )
                    self.logger.info(f"Decremented referral count for inviter {inviter_id}")
                
                await db.commit()
                return True
                
        except Exception as e:
            self.logger.error(f"Error removing user: {e}", exc_info=True)
            return False

    async def get_total_referrals(self, telegram_id: int) -> int:
        """Get total number of users referred by a user"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                async with db.execute(
                    'SELECT COUNT(*) FROM users WHERE inviter_id = ?',
                    (telegram_id,)
                ) as cursor:
                    result = await cursor.fetchone()
                    count = result[0] if result else 0
                    self.logger.info(f"User {telegram_id} has {count} total referrals")
                    return count
        except Exception as e:
            self.logger.error(f"Error getting total referrals: {e}", exc_info=True)
            return 0

    async def get_active_referrals(self, telegram_id: int) -> int:
        """Get number of active referrals (who have chatted) for a user"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                async with db.execute(
                    '''
                    SELECT COUNT(*) 
                    FROM users 
                    WHERE inviter_id = ? 
                    AND is_member = TRUE 
                    AND has_chatted = TRUE
                    ''',
                    (telegram_id,)
                ) as cursor:
                    result = await cursor.fetchone()
                    count = result[0] if result else 0
                    self.logger.info(f"User {telegram_id} has {count} active chatting referrals")
                    return count
        except Exception as e:
            self.logger.error(f"Error getting active referrals: {e}", exc_info=True)
            return 0

    async def mark_user_chatted(self, telegram_id: int) -> bool:
        """Mark a user as having chatted and update inviter's referral count if needed"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                # Get user's current status and inviter
                async with db.execute(
                    'SELECT has_chatted, inviter_id FROM users WHERE telegram_id = ?',
                    (telegram_id,)
                ) as cursor:
                    result = await cursor.fetchone()
                    if not result:
                        return False
                    
                    has_chatted, inviter_id = result
                    
                    # If user hasn't chatted before
                    if not has_chatted:
                        # Mark as chatted
                        await db.execute(
                            'UPDATE users SET has_chatted = TRUE WHERE telegram_id = ?',
                            (telegram_id,)
                        )
                        
                        # If they have an inviter, increment their referral count
                        if inviter_id:
                            await db.execute(
                                'UPDATE users SET referrals = referrals + 1 WHERE telegram_id = ?',
                                (inviter_id,)
                            )
                            self.logger.info(f"Incremented referral count for inviter {inviter_id} after user {telegram_id} chatted")
                        
                        await db.commit()
                        return True
                    
                    return False
                    
        except Exception as e:
            self.logger.error(f"Error marking user as chatted: {e}", exc_info=True)
            return False

    async def get_leaderboard(self, limit: int = 10) -> list:
        """Get top inviters with active chatting referrals"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                async with db.execute(
                    '''
                    SELECT u.telegram_id, COUNT(r.telegram_id) as referral_count
                    FROM users u
                    LEFT JOIN users r ON r.inviter_id = u.telegram_id 
                        AND r.is_member = TRUE 
                        AND r.has_chatted = TRUE
                    WHERE u.is_member = TRUE
                    GROUP BY u.telegram_id
                    HAVING referral_count > 0
                    ORDER BY referral_count DESC
                    LIMIT ?
                    ''',
                    (limit,)
                ) as cursor:
                    result = await cursor.fetchall()
                    self.logger.info(f"Retrieved leaderboard with {len(result)} entries")
                    return result
        except Exception as e:
            self.logger.error(f"Error getting leaderboard: {e}", exc_info=True)
            return []

    async def clear_all_referrals(self) -> bool:
        """Reset all referral counts to zero"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute('UPDATE users SET referrals = 0')
                await db.commit()
                self.logger.info("All referral counts reset to zero")
                return True
        except Exception as e:
            self.logger.error(f"Error clearing referrals: {e}", exc_info=True)
            return False
