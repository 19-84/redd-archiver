-- Recalculate and update conspiracy subreddit statistics
UPDATE subreddit_statistics
SET
    unique_users = (
        SELECT COUNT(DISTINCT author) FROM (
            SELECT author FROM posts WHERE subreddit = 'conspiracy' AND author != '[deleted]'
            UNION
            SELECT author FROM comments WHERE subreddit = 'conspiracy' AND author != '[deleted]'
        ) AS authors
    ),
    earliest_date = (SELECT MIN(created_utc) FROM posts WHERE subreddit = 'conspiracy'),
    latest_date = (SELECT MAX(created_utc) FROM posts WHERE subreddit = 'conspiracy'),
    self_posts = (SELECT COUNT(*) FROM posts WHERE subreddit = 'conspiracy' AND is_self = true)
WHERE subreddit = 'conspiracy';

-- Verify the update
SELECT subreddit, unique_users, archived_posts, earliest_date, latest_date, self_posts FROM subreddit_statistics WHERE subreddit = 'conspiracy';
