import React, { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../services/api';
import {
    ChevronUp,
    ChevronDown,
    ChevronLeft,
    ChevronRight,
    Circle,
    Cpu,
    Link,
    Link2Off,
    Keyboard,
    Eye,
    EyeOff,
    Home,
    RotateCcw
} from 'lucide-react';
import { motion } from 'framer-motion';
import toast from 'react-hot-toast';

const RobotControl = ({ isActive = false }) => {
    const [status, setStatus] = useState({ connected: false, port: '' });
    const [isLoading, setIsLoading] = useState(false);
    const [activeCommand, setActiveCommand] = useState(null);
    const [autoFollow, setAutoFollow] = useState(false);
    const [followUnknowns, setFollowUnknowns] = useState(false);
    const [homing, setHoming] = useState(false);
    const [scanActive, setScanActive] = useState(false);
    const repeatRef = useRef(null);      // setInterval handle for held keys
    const inFlightRef = useRef(false);   // true while a command HTTP request is in flight
    const pendingCmdRef = useRef(null);  // latest command that arrived while in-flight
    const lastReconnectRef = useRef(0);  // timestamp of last auto-reconnect attempt

    const fetchStatus = useCallback(async () => {
        try {
            const res = await api.robot.getStatus();
            if (res.success) {
                setStatus(res.status);
                if (res.status.auto_follow !== undefined) setAutoFollow(res.status.auto_follow);
                if (res.status.follow_unknowns !== undefined) setFollowUnknowns(res.status.follow_unknowns);
                if (res.status.homing !== undefined) setHoming(res.status.homing);
                if (res.status.scan_active !== undefined) setScanActive(res.status.scan_active);
            }
        } catch (error) {
            console.error("Failed to fetch robot status", error);
        }
    }, []);

    useEffect(() => {
        fetchStatus();
    }, [fetchStatus]);

    // Always poll status every 2 s; auto-reconnect if the backend socket dropped.
    useEffect(() => {
        const interval = setInterval(async () => {
            await fetchStatus();
            setStatus(prev => {
                if (!prev.connected && prev.host) {
                    // Rate-limit reconnect attempts to once every 5 s.
                    const now = Date.now();
                    if (now - lastReconnectRef.current > 5000) {
                        lastReconnectRef.current = now;
                        api.robot.connect().catch(() => {});
                    }
                }
                return prev;
            });
        }, 2000);
        return () => clearInterval(interval);
    }, [fetchStatus]);

    // Faster 1 s poll while homing or scanning so buttons reset promptly.
    useEffect(() => {
        if (!homing && !scanActive) return;
        const interval = setInterval(fetchStatus, 1000);
        return () => clearInterval(interval);
    }, [homing, scanActive, fetchStatus]);

    // Named async function so it can call itself recursively to flush pending commands.
    const sendCommand = useCallback(async function send(command) {
        if (inFlightRef.current) {
            // Store the latest command; STOP always takes priority over motion.
            if (command === 'S' || pendingCmdRef.current !== 'S') {
                pendingCmdRef.current = command;
            }
            return;
        }
        inFlightRef.current = true;
        pendingCmdRef.current = null;
        setActiveCommand(command);
        try {
            const res = await api.robot.control(command);
            if (!res.success) toast.error(res.message);
        } catch {
            toast.error("Failed to send command");
        } finally {
            inFlightRef.current = false;
            setTimeout(() => setActiveCommand(null), 150);
            // Immediately flush any command that arrived while we were in-flight.
            const next = pendingCmdRef.current;
            if (next !== null) {
                pendingCmdRef.current = null;
                send(next);
            }
        }
    }, []);

    const handleConnect = async () => {
        setIsLoading(true);
        try {
            const res = await api.robot.connect();
            if (res.success) {
                toast.success(res.message);
                fetchStatus();
            } else {
                toast.error(res.message);
            }
        } catch (error) {
            toast.error("Connection failed");
        } finally {
            setIsLoading(false);
        }
    };

    const handleDisconnect = async () => {
        setIsLoading(true);
        try {
            const res = await api.robot.disconnect();
            if (res.success) {
                toast.success(res.message);
                fetchStatus();
            } else {
                toast.error(res.message);
            }
        } catch (error) {
            toast.error("Disconnect failed");
        } finally {
            setIsLoading(false);
        }
    };

    const handleToggleFollow = async () => {
        const newState = !autoFollow;
        try {
            const res = await api.robot.toggleFollow(newState);
            if (res.success) {
                setAutoFollow(newState);
                toast.success(res.message);
            } else {
                toast.error(res.message);
            }
        } catch (error) {
            toast.error("Failed to toggle auto-follow");
        }
    };

    const handleToggleFollowUnknowns = async () => {
        const newState = !followUnknowns;
        try {
            const res = await api.robot.toggleFollowUnknowns(newState);
            if (res.success) {
                setFollowUnknowns(newState);
                toast.success(newState ? 'Now tracking unknown persons' : 'Unknown tracking disabled');
            } else {
                toast.error(res.message);
            }
        } catch (error) {
            toast.error("Failed to toggle follow-unknowns");
        }
    };

    const handleRegisterHome = async () => {
        try {
            const res = await api.robot.registerHome();
            if (res.success) {
                toast.success('Home position saved — robot will return here on detection');
            } else {
                toast.error(res.message || 'Failed to register home');
            }
        } catch (error) {
            toast.error('Failed to register home position');
        }
    };

    const handleReturnHome = async () => {
        try {
            const res = await api.robot.returnHome();
            if (res.success) {
                toast.success('Returning to home position');
                fetchStatus();
            } else {
                toast.error(res.message || 'Failed to return home');
            }
        } catch (error) {
            toast.error('Failed to send return home command');
        }
    };

    useEffect(() => {
        const KEY_TO_CMD = {
            w: 'F', arrowup: 'F',
            s: 'B', arrowdown: 'B',
            a: 'L', arrowleft: 'L',
            d: 'R', arrowright: 'R',
            ' ': 'S',
        };
        // Re-send interval must be less than the ESP32's 300ms auto-stop timeout.
        const REPEAT_MS = 150;

        const stopRepeat = () => {
            if (repeatRef.current) {
                clearInterval(repeatRef.current);
                repeatRef.current = null;
            }
        };

        const handleKeyDown = (e) => {
            if (!isActive || !status.connected) return;
            const tag = document.activeElement?.tagName.toLowerCase();
            if (tag === 'input' || tag === 'textarea' || tag === 'select') return;

            const cmd = KEY_TO_CMD[e.key.toLowerCase()];
            if (!cmd) return;
            e.preventDefault();

            // Ignore OS key-repeat events — we drive repetition ourselves.
            if (e.repeat) return;

            stopRepeat();
            sendCommand(cmd);

            // STOP is a one-shot — no repeat needed.
            if (cmd !== 'S') {
                repeatRef.current = setInterval(() => sendCommand(cmd), REPEAT_MS);
            }
        };

        const handleKeyUp = (e) => {
            if (!isActive || !status.connected) return;
            const cmd = KEY_TO_CMD[e.key.toLowerCase()];
            if (!cmd || cmd === 'S') return;

            stopRepeat();
            sendCommand('S');
        };

        window.addEventListener('keydown', handleKeyDown);
        window.addEventListener('keyup', handleKeyUp);
        return () => {
            window.removeEventListener('keydown', handleKeyDown);
            window.removeEventListener('keyup', handleKeyUp);
            stopRepeat();
        };
    }, [status.connected, isActive, sendCommand]);

    const ControlButton = ({ command, icon: Icon, label }) => (
        <motion.button
            whileTap={{ scale: 0.9 }}
            onClick={() => sendCommand(command)}
            disabled={!status.connected}
            className={`
                p-4 rounded-2xl flex flex-col items-center justify-center gap-2 transition-all
                ${!status.connected
                    ? 'bg-neutral-800/30 text-neutral-600 cursor-not-allowed'
                    : activeCommand === command
                        ? 'bg-purple-500 text-white shadow-[0_0_20px_rgba(168,85,247,0.4)]'
                        : 'bg-neutral-800 text-neutral-400 hover:bg-neutral-700 hover:text-white'
                }
            `}
        >
            <Icon size={32} />
            <span className="text-[10px] uppercase tracking-widest font-bold">{label}</span>
        </motion.button>
    );

    return (
        <div className="p-6 space-y-8 h-full">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${status.connected ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                        <Cpu size={20} />
                    </div>
                    <div>
                        <h3 className="font-bold text-white">Robot Status</h3>
                        <p className="text-xs text-neutral-400">
                            {status.connected ? `Connected to ${status.port}` : 'Disconnected'}
                        </p>
                    </div>
                </div>

                <button
                    onClick={status.connected ? handleDisconnect : handleConnect}
                    disabled={isLoading}
                    className={`
                        px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2
                        ${status.connected
                            ? 'bg-neutral-800 text-red-400 hover:bg-red-500/10'
                            : 'bg-purple-600 text-white hover:bg-purple-700 shadow-lg shadow-purple-500/20'
                        }
                    `}
                >
                    {isLoading ? (
                        <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                    ) : status.connected ? (
                        <>
                            <Link2Off size={16} />
                            Disconnect
                        </>
                    ) : (
                        <>
                            <Link size={16} />
                            Connect
                        </>
                    )}
                </button>
            </div>

            <div className="grid grid-cols-3 gap-4 max-w-[300px] mx-auto">
                <div />
                <ControlButton command="F" icon={ChevronUp} label="Forward" />
                <div />

                <ControlButton command="L" icon={ChevronLeft} label="Left" />
                <ControlButton command="S" icon={Circle} label="Stop" />
                <ControlButton command="R" icon={ChevronRight} label="Right" />

                <div />
                <ControlButton command="B" icon={ChevronDown} label="Backward" />
                <div />
            </div>

            <div className="space-y-3">
                <div
                    onClick={handleToggleFollow}
                    className={`
                        p-4 rounded-xl flex items-center justify-between cursor-pointer transition-all border
                        ${autoFollow
                            ? 'bg-purple-600/10 border-purple-500/50 text-purple-400'
                            : 'bg-neutral-800 border-white/5 text-neutral-400 hover:bg-neutral-700'
                        }
                    `}
                >
                    <div className="flex items-center gap-3">
                        {autoFollow ? <Eye size={20} /> : <EyeOff size={20} />}
                        <div>
                            <h4 className="text-sm font-bold">Auto-Follow Person</h4>
                            <p className="text-[10px] opacity-70">Robot follows the largest detected person</p>
                        </div>
                    </div>
                    <div className={`
                        w-10 h-6 rounded-full p-1 transition-colors
                        ${autoFollow ? 'bg-purple-500' : 'bg-neutral-600'}
                    `}>
                        <motion.div
                            animate={{ x: autoFollow ? 16 : 0 }}
                            className="w-4 h-4 bg-white rounded-full"
                        />
                    </div>
                </div>

                <div
                    onClick={handleToggleFollowUnknowns}
                    className={`
                        p-4 rounded-xl flex items-center justify-between cursor-pointer transition-all border
                        ${followUnknowns
                            ? 'bg-red-600/10 border-red-500/50 text-red-400'
                            : 'bg-neutral-800 border-white/5 text-neutral-400 hover:bg-neutral-700'
                        }
                    `}
                >
                    <div className="flex items-center gap-3">
                        <div className={`text-lg leading-none ${followUnknowns ? 'animate-pulse' : ''}`}>🚨</div>
                        <div>
                            <h4 className="text-sm font-bold">Follow Unknown Person</h4>
                            <p className="text-[10px] opacity-70">Robot intercepts unrecognised persons from static camera</p>
                        </div>
                    </div>
                    <div className={`
                        w-10 h-6 rounded-full p-1 transition-colors
                        ${followUnknowns ? 'bg-red-500' : 'bg-neutral-600'}
                    `}>
                        <motion.div
                            animate={{ x: followUnknowns ? 16 : 0 }}
                            className="w-4 h-4 bg-white rounded-full"
                        />
                    </div>
                </div>

                <div className="bg-neutral-800/50 rounded-xl p-4 flex items-center gap-4 border border-white/5">
                    <div className="p-2 bg-neutral-900 rounded-lg text-purple-400">
                        <Keyboard size={20} />
                    </div>
                    <div>
                        <h4 className="text-sm font-medium text-white">Keyboard Controls</h4>
                        <p className="text-[11px] text-neutral-500">Use WASD or Arrows to move. Space to stop.</p>
                    </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                    <motion.button
                        whileTap={{ scale: 0.97 }}
                        onClick={handleReturnHome}
                        disabled={!status.connected || homing}
                        className={`
                            p-4 rounded-xl flex items-center gap-3 transition-all border
                            ${!status.connected || homing
                                ? 'bg-neutral-800/30 border-white/5 text-neutral-600 cursor-not-allowed'
                                : 'bg-blue-500/10 border-blue-500/30 text-blue-400 hover:bg-blue-500/20'
                            }
                        `}
                    >
                        <RotateCcw size={20} className={homing ? 'animate-spin' : ''} />
                        <div className="text-left">
                            <h4 className="text-sm font-bold">Return Home</h4>
                            <p className="text-[10px] opacity-70">
                                {homing ? 'Returning…' : 'Go back to home position'}
                            </p>
                        </div>
                    </motion.button>

                    <motion.button
                        whileTap={{ scale: 0.97 }}
                        onClick={handleRegisterHome}
                        disabled={!status.connected}
                        className={`
                            p-4 rounded-xl flex items-center gap-3 transition-all border
                            ${!status.connected
                                ? 'bg-neutral-800/30 border-white/5 text-neutral-600 cursor-not-allowed'
                                : 'bg-amber-500/10 border-amber-500/30 text-amber-400 hover:bg-amber-500/20'
                            }
                        `}
                    >
                        <Home size={20} />
                        <div className="text-left">
                            <h4 className="text-sm font-bold">Set Home</h4>
                            <p className="text-[10px] opacity-70">Save current spot as home</p>
                        </div>
                    </motion.button>
                </div>

                {(homing || scanActive) && (
                    <div className={`
                        p-4 rounded-xl flex items-center gap-3 border
                        ${homing
                            ? 'bg-blue-500/10 border-blue-500/30 text-blue-400'
                            : 'bg-orange-500/10 border-orange-500/30 text-orange-400'
                        }
                    `}>
                        <RotateCcw size={20} className="animate-spin" />
                        <div>
                            <h4 className="text-sm font-bold">
                                {homing ? 'Returning to Home…' : 'Scanning for Target…'}
                            </h4>
                            <p className="text-[10px] opacity-70">
                                {homing
                                    ? 'Robot is navigating back to camera install position'
                                    : 'Robot arrived home and is rotating to locate the target'
                                }
                            </p>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default RobotControl;
