-- Allow all realms to enter any dungeon (NPCs scale to player BP anyway)
UPDATE dungeons_catalog SET max_realm = 10;
