import Fastify from 'fastify';
import cors from '@fastify/cors';
import websocket from '@fastify/websocket';
import { v4 as uuidv4 } from 'uuid';

// ============================================================================
// 🚀 ENTERPRISE CONFIGURATION
// ============================================================================
const CONFIG = {
    port: parseInt(process.env.PORT || '8080'),
    host: process.env.HOST || '0.0.0.0',
    antigravityUrl: process.env.ANTIGRAVITY_URL || 'http://localhost:8765',
    testMode: process.env.TEST_MODE === 'true',

    // Enterprise Settings
    sessionExpiry: 60 * 60 * 1000,      // 1 hour
    heartbeatInterval: 10000,            // 10 seconds
    heartbeatTimeout: 30000,             // 30 seconds
    rateLimitWindow: 60000,              // 1 minute
    rateLimitMax: 1000,                  // 1000 requests per minute
    maxSessionsPerIP: 5,
    cleanupInterval: 60000               // 1 minute
};

// ============================================================================
// 📊 ENTERPRISE DATA STRUCTURES
// ============================================================================
const sessions = new Map();           // sessionId -> SessionData
const connections = {
    agents: new Map(),                // sessionId -> ConnectionData
    mobiles: new Map()                // sessionId -> ConnectionData
};
const rateLimits = new Map();         // ip -> { count, resetTime }
const connectionMetrics = new Map();  // sessionId -> MetricsData

// Connection Data Structure
class ConnectionData {
    constructor(socket, clientType, sessionId) {
        this.socket = socket;
        this.clientType = clientType;
        this.sessionId = sessionId;
        this.connectedAt = Date.now();
        this.lastHeartbeat = Date.now();
        this.latency = 0;
        this.framesSent = 0;
        this.bytesTransferred = 0;
        this.state = 'connected'; // connected, streaming, idle
    }
}

// Session Data Structure
class SessionData {
    constructor(id, creatorIP) {
        this.id = id;
        this.createdAt = Date.now();
        this.expiresAt = Date.now() + CONFIG.sessionExpiry;
        this.status = 'pending';
        this.creatorIP = creatorIP;
        this.agentConnected = false;
        this.mobileConnected = false;
        this.totalFrames = 0;
        this.totalBytes = 0;
    }
}

// ============================================================================
// 🛡️ RATE LIMITING
// ============================================================================
function checkRateLimit(ip) {
    const now = Date.now();
    let limit = rateLimits.get(ip);

    if (!limit || now > limit.resetTime) {
        limit = { count: 0, resetTime: now + CONFIG.rateLimitWindow };
        rateLimits.set(ip, limit);
    }

    limit.count++;
    return limit.count <= CONFIG.rateLimitMax;
}

// ============================================================================
// 🧹 CLEANUP ROUTINES
// ============================================================================
function cleanupExpiredSessions() {
    const now = Date.now();
    let cleaned = 0;

    for (const [sessionId, session] of sessions) {
        if (now > session.expiresAt) {
            // Close connections
            const agent = connections.agents.get(sessionId);
            const mobile = connections.mobiles.get(sessionId);

            if (agent?.socket?.readyState === 1) {
                agent.socket.send(JSON.stringify({ type: 'session_expired' }));
                agent.socket.close();
            }
            if (mobile?.socket?.readyState === 1) {
                mobile.socket.send(JSON.stringify({ type: 'session_expired' }));
                mobile.socket.close();
            }

            connections.agents.delete(sessionId);
            connections.mobiles.delete(sessionId);
            connectionMetrics.delete(sessionId);
            sessions.delete(sessionId);
            cleaned++;
        }
    }

    if (cleaned > 0) {
        app.log.info(`Cleaned ${cleaned} expired sessions`);
    }
}

function checkHeartbeats() {
    const now = Date.now();

    for (const [sessionId, conn] of connections.agents) {
        if (now - conn.lastHeartbeat > CONFIG.heartbeatTimeout) {
            app.log.warn(`Agent heartbeat timeout: ${sessionId}`);
            conn.socket.close();
            connections.agents.delete(sessionId);
        }
    }

    for (const [sessionId, conn] of connections.mobiles) {
        if (now - conn.lastHeartbeat > CONFIG.heartbeatTimeout) {
            app.log.warn(`Mobile heartbeat timeout: ${sessionId}`);
            conn.socket.close();
            connections.mobiles.delete(sessionId);
        }
    }
}

// Start cleanup intervals
setInterval(cleanupExpiredSessions, CONFIG.cleanupInterval);
setInterval(checkHeartbeats, CONFIG.heartbeatInterval);

// ============================================================================
// 🚀 FASTIFY SERVER SETUP
// ============================================================================
const app = Fastify({
    logger: true,
    trustProxy: true  // For rate limiting behind proxy
});

await app.register(cors, { origin: true });
await app.register(websocket);

// ============================================================================
// 📡 ENTERPRISE REST API
// ============================================================================

// Health check with detailed metrics
app.get('/api/health', async (request) => {
    const ip = request.ip;
    if (!checkRateLimit(ip)) {
        return { error: 'Rate limit exceeded', retryAfter: 60 };
    }

    // Calculate uptime and stats
    const activeAgents = [...connections.agents.values()].filter(c => c.socket.readyState === 1).length;
    const activeMobiles = [...connections.mobiles.values()].filter(c => c.socket.readyState === 1).length;

    return {
        status: 'ok',
        version: '2.0.0-enterprise',
        timestamp: Date.now(),
        uptime: process.uptime(),
        sessions: {
            total: sessions.size,
            active: activeAgents + activeMobiles
        },
        connections: {
            agents: activeAgents,
            mobiles: activeMobiles
        },
        limits: {
            sessionExpiry: CONFIG.sessionExpiry / 1000 / 60 + ' minutes',
            heartbeatInterval: CONFIG.heartbeatInterval / 1000 + ' seconds',
            rateLimit: CONFIG.rateLimitMax + ' per minute'
        }
    };
});

// Create session with metadata
app.post('/api/sessions', async (request, reply) => {
    const ip = request.ip;

    if (!checkRateLimit(ip)) {
        return reply.status(429).send({ error: 'Rate limit exceeded' });
    }

    // Check max sessions per IP
    let ipSessions = 0;
    for (const session of sessions.values()) {
        if (session.creatorIP === ip) ipSessions++;
    }
    if (ipSessions >= CONFIG.maxSessionsPerIP) {
        return reply.status(429).send({ error: 'Max sessions per IP exceeded' });
    }

    const sessionId = uuidv4();
    const session = new SessionData(sessionId, ip);
    sessions.set(sessionId, session);

    app.log.info(`Session created: ${sessionId} from ${ip}`);

    return {
        sessionId,
        status: 'created',
        expiresAt: session.expiresAt,
        expiresIn: CONFIG.sessionExpiry / 1000 / 60 + ' minutes'
    };
});

// Get session status with metrics
app.get('/api/sessions/:sessionId', async (request, reply) => {
    const { sessionId } = request.params;
    const session = sessions.get(sessionId);

    if (!session) {
        return reply.status(404).send({ error: 'Session not found' });
    }

    const agentConn = connections.agents.get(sessionId);
    const mobileConn = connections.mobiles.get(sessionId);

    return {
        ...session,
        agentConnected: agentConn?.socket?.readyState === 1,
        mobileConnected: mobileConn?.socket?.readyState === 1,
        agentLatency: agentConn?.latency || null,
        mobileLatency: mobileConn?.latency || null,
        expiresIn: Math.max(0, session.expiresAt - Date.now()) / 1000 + ' seconds'
    };
});

// Get latest active session
app.get('/api/sessions/latest', async (request, reply) => {
    // Find session with active agent
    for (const [sessionId, conn] of connections.agents) {
        if (conn.socket.readyState === 1) {
            const session = sessions.get(sessionId);
            if (session) {
                return {
                    sessionId,
                    ...session,
                    agentConnected: true,
                    agentLatency: conn.latency,
                    mobileConnected: connections.mobiles.has(sessionId)
                };
            }
        }
    }

    // No active agent, return most recent session
    let latestSession = null;
    for (const [id, session] of sessions) {
        if (!latestSession || session.createdAt > latestSession.createdAt) {
            latestSession = { sessionId: id, ...session };
        }
    }

    if (latestSession) return latestSession;
    return reply.status(404).send({ error: 'No sessions available' });
});

// List all sessions (admin endpoint)
app.get('/api/sessions', async (request, reply) => {
    const sessionList = [];
    for (const [id, session] of sessions) {
        const agentConn = connections.agents.get(id);
        const mobileConn = connections.mobiles.get(id);

        sessionList.push({
            id,
            createdAt: session.createdAt,
            expiresAt: session.expiresAt,
            agentConnected: agentConn?.socket?.readyState === 1,
            mobileConnected: mobileConn?.socket?.readyState === 1,
            totalFrames: session.totalFrames,
            totalBytes: session.totalBytes
        });
    }
    return { sessions: sessionList, count: sessionList.length };
});

// Delete session (admin endpoint)
app.delete('/api/sessions/:sessionId', async (request, reply) => {
    const { sessionId } = request.params;

    if (!sessions.has(sessionId)) {
        return reply.status(404).send({ error: 'Session not found' });
    }

    // Close connections
    const agent = connections.agents.get(sessionId);
    const mobile = connections.mobiles.get(sessionId);

    if (agent?.socket?.readyState === 1) {
        agent.socket.send(JSON.stringify({ type: 'session_terminated' }));
        agent.socket.close();
    }
    if (mobile?.socket?.readyState === 1) {
        mobile.socket.send(JSON.stringify({ type: 'session_terminated' }));
        mobile.socket.close();
    }

    connections.agents.delete(sessionId);
    connections.mobiles.delete(sessionId);
    sessions.delete(sessionId);

    return { success: true, message: 'Session terminated' };
});

// Server metrics
app.get('/api/metrics', async () => {
    let totalFrames = 0;
    let totalBytes = 0;

    for (const session of sessions.values()) {
        totalFrames += session.totalFrames;
        totalBytes += session.totalBytes;
    }

    return {
        uptime: process.uptime(),
        memory: process.memoryUsage(),
        sessions: sessions.size,
        connections: {
            agents: connections.agents.size,
            mobiles: connections.mobiles.size
        },
        traffic: {
            totalFrames,
            totalBytes,
            totalMB: (totalBytes / 1024 / 1024).toFixed(2)
        }
    };
});

// ============================================================================
// 🔌 ENTERPRISE WEBSOCKET RELAY
// ============================================================================
app.register(async function (fastify) {
    fastify.get('/ws/relay', { websocket: true }, (socket, req) => {
        let clientType = null;
        let sessionId = null;
        let connectionData = null;

        const clientIP = req.ip;
        app.log.info(`New WebSocket connection from ${clientIP}`);

        // Setup heartbeat ping
        const heartbeatPing = setInterval(() => {
            if (socket.readyState === 1) {
                const pingTime = Date.now();
                socket.send(JSON.stringify({
                    type: 'ping',
                    timestamp: pingTime,
                    serverTime: new Date().toISOString()
                }));
            }
        }, CONFIG.heartbeatInterval);

        socket.on('message', (rawMessage) => {
            try {
                // Track bandwidth
                const messageSize = rawMessage.length || rawMessage.byteLength || 0;
                if (connectionData) {
                    connectionData.bytesTransferred += messageSize;
                }

                const message = JSON.parse(rawMessage.toString());

                // Handle heartbeat pong
                if (message.type === 'pong') {
                    if (connectionData) {
                        connectionData.lastHeartbeat = Date.now();
                        connectionData.latency = Date.now() - (message.timestamp || Date.now());
                    }
                    return;
                }

                // Handle authentication
                if (message.type === 'auth') {
                    sessionId = message.sessionId;
                    clientType = message.clientType;

                    // Validate or create session
                    if (!sessions.has(sessionId)) {
                        if (CONFIG.testMode) {
                            sessions.set(sessionId, new SessionData(sessionId, clientIP));
                        } else {
                            socket.send(JSON.stringify({
                                type: 'error',
                                message: 'Invalid session'
                            }));
                            return;
                        }
                    }

                    // Check session expiry
                    const session = sessions.get(sessionId);
                    if (Date.now() > session.expiresAt) {
                        socket.send(JSON.stringify({
                            type: 'error',
                            message: 'Session expired'
                        }));
                        return;
                    }

                    // Create connection data
                    connectionData = new ConnectionData(socket, clientType, sessionId);

                    // Register connection
                    if (clientType === 'agent') {
                        connections.agents.set(sessionId, connectionData);
                        session.agentConnected = true;
                        app.log.info(`✅ Agent connected: ${sessionId}`);
                    } else if (clientType === 'mobile') {
                        connections.mobiles.set(sessionId, connectionData);
                        session.mobileConnected = true;
                        app.log.info(`✅ Mobile connected: ${sessionId}`);
                    }

                    // Refresh session expiry on connect
                    session.expiresAt = Date.now() + CONFIG.sessionExpiry;

                    // Send confirmation with server info
                    socket.send(JSON.stringify({
                        type: 'auth_success',
                        sessionId,
                        clientType,
                        serverVersion: '2.0.0-enterprise',
                        heartbeatInterval: CONFIG.heartbeatInterval,
                        sessionExpiresAt: session.expiresAt
                    }));

                    // Notify paired client
                    const paired = clientType === 'agent'
                        ? connections.mobiles.get(sessionId)
                        : connections.agents.get(sessionId);

                    if (paired?.socket?.readyState === 1) {
                        paired.socket.send(JSON.stringify({
                            type: 'peer_connected',
                            peerType: clientType,
                            timestamp: Date.now()
                        }));
                    }
                    return;
                }

                // Relay messages between paired clients
                if (sessionId && clientType) {
                    const target = clientType === 'agent'
                        ? connections.mobiles.get(sessionId)
                        : connections.agents.get(sessionId);

                    if (target?.socket?.readyState === 1) {
                        // Track frame statistics
                        const session = sessions.get(sessionId);
                        if (session && message.type === 'frame') {
                            session.totalFrames++;
                            session.totalBytes += messageSize;
                            if (connectionData) {
                                connectionData.framesSent++;
                                connectionData.state = 'streaming';
                            }
                        }

                        // Forward raw message for efficiency
                        target.socket.send(rawMessage);
                    }
                }

            } catch (error) {
                app.log.error(`Message parse error: ${error.message}`);
            }
        });

        socket.on('close', () => {
            clearInterval(heartbeatPing);

            if (sessionId && clientType) {
                const session = sessions.get(sessionId);

                if (clientType === 'agent') {
                    connections.agents.delete(sessionId);
                    if (session) session.agentConnected = false;
                } else {
                    connections.mobiles.delete(sessionId);
                    if (session) session.mobileConnected = false;
                }

                app.log.info(`❌ ${clientType} disconnected: ${sessionId}`);

                // Notify paired client
                const paired = clientType === 'agent'
                    ? connections.mobiles.get(sessionId)
                    : connections.agents.get(sessionId);

                if (paired?.socket?.readyState === 1) {
                    paired.socket.send(JSON.stringify({
                        type: 'peer_disconnected',
                        peerType: clientType,
                        timestamp: Date.now()
                    }));
                }
            }
        });

        socket.on('error', (error) => {
            app.log.error(`WebSocket error: ${error.message}`);
        });
    });
});

// ============================================================================
// 🚀 START SERVER
// ============================================================================
try {
    await app.listen({ port: CONFIG.port, host: CONFIG.host });
    console.log(`
╔══════════════════════════════════════════════════════════════════╗
║     🚀 Antigravity Remote Control - ENTERPRISE SERVER            ║
║                      Version 2.0.0                                ║
╠══════════════════════════════════════════════════════════════════╣
║  REST API:      http://${CONFIG.host}:${CONFIG.port}/api                          ║
║  WebSocket:     ws://${CONFIG.host}:${CONFIG.port}/ws/relay                       ║
╠══════════════════════════════════════════════════════════════════╣
║  Session Expiry:    ${CONFIG.sessionExpiry / 1000 / 60} minutes                                    ║
║  Heartbeat:         ${CONFIG.heartbeatInterval / 1000} seconds                                    ║
║  Rate Limit:        ${CONFIG.rateLimitMax}/minute                                ║
║  Test Mode:         ${CONFIG.testMode ? 'ENABLED' : 'DISABLED'}                                       ║
╚══════════════════════════════════════════════════════════════════╝
    `);
} catch (err) {
    app.log.error(err);
    process.exit(1);
}
