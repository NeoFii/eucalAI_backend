-- Token bucket rate limiter
-- KEYS[1] = hash key (fields: tokens, last_refill)
-- ARGV[1] = capacity (max tokens)
-- ARGV[2] = refill_rate (tokens per second)
-- ARGV[3] = cost (tokens to consume, typically 1)
local now = redis.call('TIME')
local now_s = tonumber(now[1]) + tonumber(now[2]) / 1000000
local tokens = tonumber(redis.call('HGET', KEYS[1], 'tokens'))
local last = tonumber(redis.call('HGET', KEYS[1], 'last_refill'))
if not tokens or not last then
    tokens = tonumber(ARGV[1])
    last = now_s
else
    local elapsed = now_s - last
    tokens = math.min(tonumber(ARGV[1]), tokens + elapsed * tonumber(ARGV[2]))
    last = now_s
end
if tokens < tonumber(ARGV[3]) then
    redis.call('HSET', KEYS[1], 'tokens', tokens, 'last_refill', last)
    redis.call('EXPIRE', KEYS[1], 120)
    return 0
end
tokens = tokens - tonumber(ARGV[3])
redis.call('HSET', KEYS[1], 'tokens', tokens, 'last_refill', last)
redis.call('EXPIRE', KEYS[1], 120)
return 1
