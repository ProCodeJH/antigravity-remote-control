import Fastify from 'fastify';
import cors from '@fastify/cors';
import websocket from '@fastify/websocket';
import { v4 as uuidv4 } from 'uuid';

// ============================================================================
// Configuration
// ============================================================================
const CONFIG = {
    port: parseInt(process.env.PORT || '8080'),
    host: process.env.HOST || '0.0.0.0',
    antigravityUrl: process.env.ANTIGRAVITY_URL || 'http://localhost:8765',
    testMode: process.env.TEST_MODE === 'true'
};

// ============================================================================
// Session Store (In-Memory)
// ============================================================================
const sessions = new Map();
const connections = {
    agents: new Map(),   // sessionId -> WebSocket
    mobiles: new Map()   // sessionId -> WebSocket
};

// ============================================================================
// Fastify Server Setup
// ============================================================================
const app = Fastify({ logger: true });

await app.register(cors, { origin: true });
await app.register(websocket);

// ============================================================================
// REST API Endpoints
// ============================================================================

// Health check
app.get('/api/health', async () => {
    return {
        status: 'ok',
        timestamp: Date.now(),
        sessions: sessions.size,
        agents: connections.agents.size,
        mobiles: connections.mobiles.size
    };
});

// Create session
app.post('/api/sessions', async (request, reply) => {
    const sessionId = uuidv4();
    const session = {
        id: sessionId,
        createdAt: Date.now(),
        status: 'pending',
        agentConnected: false,
        mobileConnected: false
    };
    sessions.set(sessionId, session);

    app.log.info(`Session created: ${sessionId}`);
    return { sessionId, status: 'created' };
});

// Get session status
app.get('/api/sessions/:sessionId', async (request, reply) => {
    const { sessionId } = request.params;
    const session = sessions.get(sessionId);

    if (!session) {
        return reply.status(404).send({ error: 'Session not found' });
    }

    return {
        ...session,
        agentConnected: connections.agents.has(sessionId),
        mobileConnected: connections.mobiles.has(sessionId)
    };
});

// Forward command to Antigravity
app.post('/api/command', async (request, reply) => {
    const { sessionId, command, type } = request.body;

    // Forward to Antigravity API
    try {
        const response = await fetch(`${CONFIG.antigravityUrl}/api/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command, type })
        });
        const result = await response.json();
        return result;
    } catch (error) {
        app.log.error(`Antigravity API error: ${error.message}`);
        return { success: false, error: error.message };
    }
});

// Get system status from Antigravity
app.get('/api/status', async (request, reply) => {
    try {
        const response = await fetch(`${CONFIG.antigravityUrl}/api/status`);
        const status = await response.json();
        return status;
    } catch (error) {
        return { error: 'Antigravity not reachable', details: error.message };
    }
});

// ============================================================================
// WebSocket Relay
// ============================================================================
app.register(async function (fastify) {
    fastify.get('/ws/relay', { websocket: true }, (socket, req) => {
        let clientType = null;
        let sessionId = null;

        app.log.info('New WebSocket connection');

        socket.on('message', (rawMessage) => {
            try {
                const message = JSON.parse(rawMessage.toString());

                // Handle authentication
                if (message.type === 'auth') {
                    sessionId = message.sessionId;
                    clientType = message.clientType; // 'agent' or 'mobile'

                    // Validate or create session
                    if (!sessions.has(sessionId)) {
                        if (CONFIG.testMode) {
                            // Auto-create session in test mode
                            sessions.set(sessionId, {
                                id: sessionId,
                                createdAt: Date.now(),
                                status: 'active'
                            });
                        } else {
                            socket.send(JSON.stringify({
                                type: 'error',
                                message: 'Invalid session'
                            }));
                            return;
                        }
                    }

                    // Register connection
                    if (clientType === 'agent') {
                        connections.agents.set(sessionId, socket);
                        app.log.info(`Agent connected: ${sessionId}`);
                    } else if (clientType === 'mobile') {
                        connections.mobiles.set(sessionId, socket);
                        app.log.info(`Mobile connected: ${sessionId}`);
                    }

                    // Send confirmation
                    socket.send(JSON.stringify({
                        type: 'auth_success',
                        sessionId,
                        clientType
                    }));

                    // Notify paired client
                    const paired = clientType === 'agent'
                        ? connections.mobiles.get(sessionId)
                        : connections.agents.get(sessionId);

                    if (paired && paired.readyState === 1) {
                        paired.send(JSON.stringify({
                            type: 'peer_connected',
                            peerType: clientType
                        }));
                    }
                    return;
                }

                // Relay messages between paired clients
                if (sessionId && clientType) {
                    const target = clientType === 'agent'
                        ? connections.mobiles.get(sessionId)
                        : connections.agents.get(sessionId);

                    if (target && target.readyState === 1) {
                        // Forward raw message for binary efficiency
                        target.send(rawMessage);
                    }
                }

            } catch (error) {
                app.log.error(`Message parse error: ${error.message}`);
            }
        });

        socket.on('close', () => {
            if (sessionId && clientType) {
                if (clientType === 'agent') {
                    connections.agents.delete(sessionId);
                } else {
                    connections.mobiles.delete(sessionId);
                }
                app.log.info(`${clientType} disconnected: ${sessionId}`);

                // Notify paired client
                const paired = clientType === 'agent'
                    ? connections.mobiles.get(sessionId)
                    : connections.agents.get(sessionId);

                if (paired && paired.readyState === 1) {
                    paired.send(JSON.stringify({
                        type: 'peer_disconnected',
                        peerType: clientType
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
// Start Server
// ============================================================================
try {
    await app.listen({ port: CONFIG.port, host: CONFIG.host });
    console.log(`
╔══════════════════════════════════════════════════════════════╗
║     🚀 Antigravity Remote Control Server                     ║
╠══════════════════════════════════════════════════════════════╣
║  REST API:    http://${CONFIG.host}:${CONFIG.port}/api       ║
║  WebSocket:   ws://${CONFIG.host}:${CONFIG.port}/ws/relay    ║
║  Test Mode:   ${CONFIG.testMode ? 'ENABLED' : 'DISABLED'}                                       ║
╚══════════════════════════════════════════════════════════════╝
    `);
} catch (err) {
    app.log.error(err);
    process.exit(1);
}
