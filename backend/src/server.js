import Fastify from 'fastify';
import cors from '@fastify/cors';
import websocket from '@fastify/websocket';
import { v4 as uuidv4 } from 'uuid';
import {
    generateToken,
    verifyToken,
    generateSecureSessionId,
    checkRateLimit,
    validateInput,
    checkConnectionLimit,
    releaseConnection,
    AUTH_CONFIG
} from './auth.js';

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
// Device Registry (멀티 네트워크 디바이스 관리)
// ============================================================================
const devices = new Map();  // deviceId -> device info

const DEVICE_TIMEOUT = 30000; // 30초 하트비트 타임아웃

function registerDevice(deviceId, info, socket) {
    const device = {
        id: deviceId,
        name: info.name || `Device-${deviceId.slice(0, 8)}`,
        hostname: info.hostname || 'unknown',
        ip: info.ip || 'unknown',
        os: info.os || 'unknown',
        antigravityStatus: info.antigravityStatus || 'unknown',
        lastHeartbeat: Date.now(),
        status: 'online',
        socket: socket,
        sessionId: info.sessionId,
        capabilities: info.capabilities || ['screen', 'input', 'command'],
        thumbnail: null
    };
    devices.set(deviceId, device);
    return device;
}

function updateDeviceHeartbeat(deviceId, data = {}) {
    const device = devices.get(deviceId);
    if (device) {
        device.lastHeartbeat = Date.now();
        device.status = 'online';
        if (data.thumbnail) device.thumbnail = data.thumbnail;
        if (data.antigravityStatus) device.antigravityStatus = data.antigravityStatus;
        if (data.systemInfo) device.systemInfo = data.systemInfo;
    }
}

function getOnlineDevices() {
    const now = Date.now();
    const result = [];
    for (const [id, device] of devices.entries()) {
        if (now - device.lastHeartbeat < DEVICE_TIMEOUT) {
            result.push({
                id: device.id,
                name: device.name,
                hostname: device.hostname,
                ip: device.ip,
                os: device.os,
                status: 'online',
                antigravityStatus: device.antigravityStatus,
                capabilities: device.capabilities,
                thumbnail: device.thumbnail,
                sessionId: device.sessionId
            });
        } else {
            device.status = 'offline';
        }
    }
    return result;
}

// Cleanup offline devices periodically
setInterval(() => {
    const now = Date.now();
    for (const [id, device] of devices.entries()) {
        if (now - device.lastHeartbeat > DEVICE_TIMEOUT * 3) {
            devices.delete(id);
        }
    }
}, 60000);

// ============================================================================
// Fastify Server Setup
// ============================================================================
const app = Fastify({ logger: true });

await app.register(cors, { origin: true });
await app.register(websocket);

// ============================================================================
// Rate Limiting Hook
// ============================================================================
app.addHook('onRequest', async (request, reply) => {
    const ip = request.ip || request.headers['x-forwarded-for'] || 'unknown';
    const rateLimit = checkRateLimit(ip);

    if (!rateLimit.allowed) {
        reply.header('X-RateLimit-Remaining', 0);
        reply.header('X-RateLimit-Reset', Math.ceil(rateLimit.resetIn / 1000));
        reply.status(429).send({
            error: 'Too many requests',
            retryAfter: Math.ceil(rateLimit.resetIn / 1000)
        });
        return;
    }

    reply.header('X-RateLimit-Remaining', rateLimit.remaining);
});

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
        mobiles: connections.mobiles.size,
        devices: devices.size
    };
});

// ============================================================================
// Device Management API (멀티 네트워크 디바이스)
// ============================================================================

// 온라인 디바이스 목록 조회
app.get('/api/devices', async () => {
    return {
        devices: getOnlineDevices(),
        total: devices.size,
        online: getOnlineDevices().length
    };
});

// 특정 디바이스 정보
app.get('/api/devices/:deviceId', async (request, reply) => {
    const { deviceId } = request.params;
    const device = devices.get(deviceId);

    if (!device) {
        return reply.status(404).send({ error: 'Device not found' });
    }

    return {
        id: device.id,
        name: device.name,
        hostname: device.hostname,
        ip: device.ip,
        os: device.os,
        status: Date.now() - device.lastHeartbeat < DEVICE_TIMEOUT ? 'online' : 'offline',
        antigravityStatus: device.antigravityStatus,
        capabilities: device.capabilities,
        sessionId: device.sessionId
    };
});

// 디바이스에 명령 전송
app.post('/api/devices/:deviceId/command', async (request, reply) => {
    const { deviceId } = request.params;
    const { command, type } = request.body;

    const device = devices.get(deviceId);
    if (!device || !device.socket || device.socket.readyState !== 1) {
        return reply.status(404).send({ error: 'Device not online' });
    }

    const commandId = `cmd_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    device.socket.send(JSON.stringify({
        type: 'command',
        commandId,
        text: command,
        cmdType: type || 'text',
        timestamp: Date.now()
    }));

    return {
        success: true,
        commandId,
        deviceId,
        status: 'sent'
    };
});

// Create session
app.post('/api/sessions', async (request, reply) => {
    const sessionId = generateSecureSessionId();
    const session = {
        id: sessionId,
        createdAt: Date.now(),
        status: 'pending',
        agentConnected: false,
        mobileConnected: false,
        expiresAt: Date.now() + AUTH_CONFIG.sessionTimeout
    };
    sessions.set(sessionId, session);

    // Generate tokens for both client types
    const agentToken = generateToken(sessionId, 'agent');
    const mobileToken = generateToken(sessionId, 'mobile');

    app.log.info(`Session created: ${sessionId}`);
    return {
        sessionId,
        status: 'created',
        tokens: { agent: agentToken, mobile: mobileToken },
        expiresIn: AUTH_CONFIG.sessionTimeout / 1000
    };
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
        let authenticated = false;
        const clientIP = req.ip || req.headers['x-forwarded-for'] || 'unknown';

        // Check connection limit
        if (!checkConnectionLimit(clientIP)) {
            socket.send(JSON.stringify({
                type: 'error',
                message: 'Too many connections from your IP'
            }));
            socket.close();
            return;
        }

        app.log.info('New WebSocket connection');

        socket.on('message', (rawMessage) => {
            try {
                const message = JSON.parse(rawMessage.toString());

                // Handle authentication
                if (message.type === 'auth') {
                    sessionId = message.sessionId;
                    clientType = message.clientType; // 'agent' or 'mobile'
                    const token = message.token;

                    // Token-based authentication (if token provided)
                    if (token) {
                        const decoded = verifyToken(token);
                        if (!decoded) {
                            socket.send(JSON.stringify({
                                type: 'error',
                                message: 'Invalid or expired token'
                            }));
                            return;
                        }
                        // Validate token matches request
                        if (decoded.sessionId !== sessionId || decoded.clientType !== clientType) {
                            socket.send(JSON.stringify({
                                type: 'error',
                                message: 'Token mismatch'
                            }));
                            return;
                        }
                    }

                    // Validate or create session
                    if (!sessions.has(sessionId)) {
                        if (CONFIG.testMode) {
                            // Auto-create session in test mode
                            sessions.set(sessionId, {
                                id: sessionId,
                                createdAt: Date.now(),
                                status: 'active',
                                expiresAt: Date.now() + AUTH_CONFIG.sessionTimeout
                            });
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
                    if (session.expiresAt && Date.now() > session.expiresAt) {
                        socket.send(JSON.stringify({
                            type: 'error',
                            message: 'Session expired'
                        }));
                        sessions.delete(sessionId);
                        return;
                    }

                    // Register connection
                    authenticated = true;
                    if (clientType === 'agent') {
                        connections.agents.set(sessionId, socket);
                        app.log.info(`Agent connected: ${sessionId}`);

                        // Device registration (멀티 네트워크 디바이스)
                        if (message.deviceInfo) {
                            const deviceId = message.deviceInfo.deviceId || sessionId;
                            registerDevice(deviceId, {
                                ...message.deviceInfo,
                                sessionId
                            }, socket);
                            app.log.info(`Device registered: ${deviceId} (${message.deviceInfo.name})`);
                        }
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

                // Require authentication for other messages
                if (!authenticated) {
                    socket.send(JSON.stringify({
                        type: 'error',
                        message: 'Not authenticated'
                    }));
                    return;
                }

                // Validate input for mobile -> agent messages
                if (clientType === 'mobile') {
                    const validation = validateInput(message);
                    if (!validation.valid) {
                        app.log.warn(`Invalid input from mobile: ${validation.error}`);
                        return; // Silently drop invalid input
                    }
                }

                // ============ Device & Heartbeat Handlers ============
                if (message.type === 'heartbeat' && clientType === 'agent') {
                    // Agent heartbeat - update device status
                    const deviceId = message.deviceId || sessionId;
                    updateDeviceHeartbeat(deviceId, {
                        thumbnail: message.thumbnail,
                        antigravityStatus: message.antigravityStatus,
                        systemInfo: message.systemInfo
                    });
                    return;
                }

                if (message.type === 'get_devices' && clientType === 'mobile') {
                    // Mobile requesting device list
                    socket.send(JSON.stringify({
                        type: 'devices',
                        devices: getOnlineDevices()
                    }));
                    return;
                }

                if (message.type === 'connect_device' && clientType === 'mobile') {
                    // Mobile wants to connect to specific device
                    const targetDevice = devices.get(message.deviceId);
                    if (targetDevice && targetDevice.socket && targetDevice.socket.readyState === 1) {
                        // Update session to point to this device
                        connections.agents.set(sessionId, targetDevice.socket);
                        socket.send(JSON.stringify({
                            type: 'device_connected',
                            deviceId: message.deviceId,
                            name: targetDevice.name
                        }));

                        // Notify the agent
                        targetDevice.socket.send(JSON.stringify({
                            type: 'mobile_connected',
                            sessionId
                        }));
                    } else {
                        socket.send(JSON.stringify({
                            type: 'error',
                            message: 'Device not available'
                        }));
                    }
                    return;
                }

                // ============ WebRTC Signaling ============
                if (message.type === 'webrtc_signal') {
                    // WebRTC 시그널링 메시지를 상대방에게 전달
                    const target = clientType === 'agent'
                        ? connections.mobiles.get(sessionId)
                        : connections.agents.get(sessionId);

                    if (target && target.readyState === 1) {
                        target.send(JSON.stringify(message));
                        app.log.info(`WebRTC signal relayed: ${message.signalType} (${clientType} -> ${clientType === 'agent' ? 'mobile' : 'agent'})`);
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
            // Release connection limit
            releaseConnection(clientIP);

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
