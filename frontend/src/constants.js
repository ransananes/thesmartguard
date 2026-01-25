export const SYSTEM_STATUS = {
    SCANNING: 'SCANNING',
    ACCESS_GRANTED: 'ACCESS_GRANTED',
    INTRUDER_ALERT: 'INTRUDER_ALERT',
};

export const STATUS_CONFIG = {
    [SYSTEM_STATUS.SCANNING]: {
        label: 'Scanning...',
        color: 'text-blue-400',
        borderColor: 'border-blue-500',
        bgColor: 'bg-blue-500/10',
        iconColor: '#60a5fa',
    },
    [SYSTEM_STATUS.ACCESS_GRANTED]: {
        label: 'Access Granted',
        color: 'text-emerald-400',
        borderColor: 'border-emerald-500',
        bgColor: 'bg-emerald-500/10',
        iconColor: '#34d399',
    },
    [SYSTEM_STATUS.INTRUDER_ALERT]: {
        label: '! INTRUDER ALERT !',
        color: 'text-red-500',
        borderColor: 'border-red-600',
        bgColor: 'bg-red-600/20',
        iconColor: '#ef4444', 
    },
};

export const MOCK_STREAM_URL = 'https://raw.githubusercontent.com/intel-iot-devkit/sample-videos/master/person-bicycle-car-detection.mp4'; // GitHub Hosted Security Feed
