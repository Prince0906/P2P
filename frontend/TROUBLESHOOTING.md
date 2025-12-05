# Troubleshooting Network Errors

## Error: "Network Error" or "AxiosError"

This means the frontend can't connect to the backend API.

### ✅ Quick Fix Steps:

1. **Check Backend is Running:**
```bash
# In Terminal 1, you should see:
# "REST API available at http://localhost:8080"
# If not, start it:
cd /Users/princesahoo/CODE/p2p
source venv/bin/activate
python cli.py start
```

2. **Test Backend Manually:**
```bash
curl http://localhost:8080/status
# Should return JSON, not an error
```

3. **Check .env.local File:**
```bash
cd /Users/princesahoo/CODE/p2p/frontend
cat .env.local
# Should show:
# NEXT_PUBLIC_API_URL=http://localhost:8080
# API_URL=http://localhost:8080
```

4. **Restart Frontend:**
```bash
# Press Ctrl+C to stop
# Then restart:
npm run dev
```

5. **Clear Browser Cache:**
- Hard refresh: `Cmd+Shift+R` (Mac) or `Ctrl+Shift+R` (Windows)
- Or open in incognito/private window

### Common Issues:

#### Issue 1: Backend Not Running
**Symptom:** Network Error
**Fix:** Start backend in Terminal 1

#### Issue 2: Wrong Port
**Symptom:** Connection refused
**Fix:** Check backend is on port 8080, or update .env.local:
```bash
echo "NEXT_PUBLIC_API_URL=http://localhost:8081" > .env.local
echo "API_URL=http://localhost:8081" >> .env.local
```

#### Issue 3: CORS Error
**Symptom:** CORS policy error in browser console
**Fix:** Backend now has CORS enabled - restart backend:
```bash
# Stop backend (Ctrl+C)
# Restart:
python cli.py start
```

#### Issue 4: Port Already in Use
**Symptom:** `OSError: [Errno 48] Address already in use`
**Fix Option 1 - Kill old process:**
```bash
# Find and kill the process
lsof -ti :8468 | xargs kill -9
lsof -ti :8469 | xargs kill -9
lsof -ti :8080 | xargs kill -9

# Or use the helper script:
./kill_old_node.sh
```

**Fix Option 2 - Use different ports:**
```bash
python cli.py --dht-port 9468 --transfer-port 9469 start --api-port 9080
# Then update frontend .env.local to match
```

### Verify Everything Works:

1. **Backend Test:**
```bash
curl http://localhost:8080/
# Should return: {"name":"P2P File Sharing System",...}
```

2. **Frontend Test:**
- Open browser console (F12)
- Check for errors
- Network tab should show successful requests to localhost:8080

3. **Full Test:**
- Upload a file
- Check activity log shows progress
- File should appear in "Shared Files" list

### Still Not Working?

1. Check firewall isn't blocking localhost
2. Try `127.0.0.1` instead of `localhost` in .env.local
3. Check both terminals are running
4. Look at browser console for detailed error messages

