local socket = require("socket")
math.randomseed(socket.gettime()*1000)
math.random();

local function randomString(length)
    local str = ""
    for i = 1, length do
        str = str .. string.char(math.random(97, 122)) -- Generates a random lowercase letter
    end
    return str
end

local function req_random()
    local method = "GET"
    local str = randomString(100)
    local path = "http://10.96.88.88:8080/ping-echo?body=" .. str
    local headers = {}
    return wrk.format(method, path, headers, str)
end

local function req_acl()
    local method = "GET"
    local path = "http://10.96.88.88:8080/ping-echo?body=test_acl"
    local headers = {}
    return wrk.format(method, path, headers, str)
end

local function req_cache()
    local method = "GET"
    local path = "http://10.96.88.88:8080/ping-echo?body=test_cache"
    local headers = {}
    return wrk.format(method, path, headers, str)
end

request = function()

    local req_rand_ratio  = 0.90
    local req_cache_ratio   = 0.05
    local req_acl_ratio  = 0.05

    local coin = math.random()
    if coin < req_rand_ratio then
        return req_random()
    elseif coin < req_rand_ratio + req_cache_ratio then
        return req_cache()
    else
        return req_acl()
    end
end
