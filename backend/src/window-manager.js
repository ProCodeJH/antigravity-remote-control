/**
 * Antigravity Remote Controller - Window Manager
 * Enterprise Multi-Terminal Session Management
 */

const pty = require('node-pty');
const EventEmitter = require('events');
const config = require('./config');

class AntigravityWindow extends EventEmitter {
    constructor(id, options = {}) {
        super();
        this.id = id;
        this.name = options.name || `Antigravity ${id}`;
        this.createdAt = new Date();
        this.lastActivity = new Date();
        this.outputBuffer = [];
        this.isRunning = true;
        this.cols = options.cols || config.windowManager.defaultCols;
        this.rows = options.rows || config.windowManager.defaultRows;

        // Initialize PTY
        this._initPty();
    }

    _initPty() {
        try {
            this.pty = pty.spawn(config.windowManager.shell, config.windowManager.shellArgs, {
                name: 'xterm-256color',
                cols: this.cols,
                rows: this.rows,
                cwd: process.env.HOME || process.env.USERPROFILE,
                env: {
                    ...process.env,
                    TERM: 'xterm-256color',
                    COLORTERM: 'truecolor'
                }
            });

            // Handle output
            this.pty.onData((data) => {
                this.lastActivity = new Date();
                this._addToBuffer(data);
                this.emit('output', { windowId: this.id, data });
            });

            // Handle exit
            this.pty.onExit(({ exitCode, signal }) => {
                this.isRunning = false;
                this.emit('exit', { windowId: this.id, exitCode, signal });
            });

            // Send initial clear and welcome
            setTimeout(() => {
                this.write('cls\r\n');
                setTimeout(() => {
                    this.write('echo Welcome to Antigravity Remote Controller!\r\n');
                }, 500);
            }, 100);

        } catch (error) {
            this.emit('error', { windowId: this.id, error: error.message });
            this.isRunning = false;
        }
    }

    _addToBuffer(data) {
        this.outputBuffer.push({
            timestamp: Date.now(),
            data
        });

        // Trim buffer if too large
        while (this.outputBuffer.length > config.windowManager.outputBufferSize) {
            this.outputBuffer.shift();
        }
    }

    /**
     * Write input to the terminal
     */
    write(data) {
        if (this.pty && this.isRunning) {
            this.pty.write(data);
            this.lastActivity = new Date();
            return true;
        }
        return false;
    }

    /**
     * Resize terminal
     */
    resize(cols, rows) {
        if (this.pty && this.isRunning) {
            this.cols = cols;
            this.rows = rows;
            this.pty.resize(cols, rows);
            return true;
        }
        return false;
    }

    /**
     * Get output buffer content
     */
    getBuffer(limit = 100) {
        return this.outputBuffer.slice(-limit);
    }

    /**
     * Clear output buffer
     */
    clearBuffer() {
        this.outputBuffer = [];
    }

    /**
     * Get window info
     */
    getInfo() {
        return {
            id: this.id,
            name: this.name,
            createdAt: this.createdAt,
            lastActivity: this.lastActivity,
            isRunning: this.isRunning,
            cols: this.cols,
            rows: this.rows,
            bufferSize: this.outputBuffer.length
        };
    }

    /**
     * Kill the terminal process
     */
    kill() {
        if (this.pty) {
            this.pty.kill();
            this.isRunning = false;
        }
    }

    /**
     * Destroy window and cleanup
     */
    destroy() {
        this.kill();
        this.removeAllListeners();
        this.outputBuffer = [];
    }
}

class WindowManager extends EventEmitter {
    constructor() {
        super();
        this.windows = new Map();
        this.nextId = 1;
    }

    /**
     * Create a new Antigravity window
     */
    createWindow(options = {}) {
        if (this.windows.size >= config.windowManager.maxWindows) {
            throw new Error(`Maximum windows (${config.windowManager.maxWindows}) reached`);
        }

        const id = this.nextId++;
        const window = new AntigravityWindow(id, options);

        // Forward events
        window.on('output', (data) => this.emit('output', data));
        window.on('exit', (data) => {
            this.emit('exit', data);
            // Auto-remove dead windows after delay
            setTimeout(() => {
                if (!window.isRunning) {
                    this.removeWindow(id);
                }
            }, 5000);
        });
        window.on('error', (data) => this.emit('error', data));

        this.windows.set(id, window);
        this.emit('created', { windowId: id, info: window.getInfo() });

        return window;
    }

    /**
     * Get window by ID
     */
    getWindow(id) {
        return this.windows.get(id);
    }

    /**
     * Get all windows info
     */
    getAllWindows() {
        return Array.from(this.windows.values()).map(w => w.getInfo());
    }

    /**
     * Remove window
     */
    removeWindow(id) {
        const window = this.windows.get(id);
        if (window) {
            window.destroy();
            this.windows.delete(id);
            this.emit('removed', { windowId: id });
            return true;
        }
        return false;
    }

    /**
     * Write to specific window
     */
    writeToWindow(id, data) {
        const window = this.windows.get(id);
        if (window) {
            return window.write(data);
        }
        return false;
    }

    /**
     * Resize window
     */
    resizeWindow(id, cols, rows) {
        const window = this.windows.get(id);
        if (window) {
            return window.resize(cols, rows);
        }
        return false;
    }

    /**
     * Get window buffer
     */
    getWindowBuffer(id, limit) {
        const window = this.windows.get(id);
        if (window) {
            return window.getBuffer(limit);
        }
        return [];
    }

    /**
     * Cleanup all windows
     */
    destroyAll() {
        for (const [id, window] of this.windows) {
            window.destroy();
        }
        this.windows.clear();
    }
}

module.exports = new WindowManager();
