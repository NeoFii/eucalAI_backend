-- Sliding window rate limiter using sorted sets
-- KEYS[1] = sorted set key
-- ARGV[1] = window_start (now - window_seconds)
-- ARGV[2] = now (used as both score and member)
-- ARGV[3] = limit
-- ARGV[4] = key TTL in seconds
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
local count = redis.call('ZCARD', KEYS[1])
if count >= tonumber(ARGV[3]) then
    return 0
end
redis.call('ZADD', KEYS[1], ARGV[2], ARGV[2])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[4]))
return 1
