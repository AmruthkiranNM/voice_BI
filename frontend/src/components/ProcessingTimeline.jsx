import { motion } from 'framer-motion';
import { TbCheck, TbLoader2 } from 'react-icons/tb';

export default function ProcessingTimeline({ pipeline, activeStageIndex }) {
  return (
    <div className="flex flex-col gap-3 pr-4 h-[300px] overflow-y-auto scrollbar-thin scrollbar-thumb-zinc-800">
      {pipeline.map((stage, index) => {
        const isCompleted = index < activeStageIndex;
        const isActive = index === activeStageIndex;
        const isPending = index > activeStageIndex;

        return (
          <motion.div
            key={stage.id}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: isPending ? 0.4 : 1, x: 0 }}
            transition={{ duration: 0.3, delay: index * 0.05 }}
            className={`flex items-center gap-4 p-3 rounded-lg border transition-colors ${
              isActive ? 'bg-zinc-800/50 border-[#9C4A2A]/40' : 'bg-transparent border-transparent'
            }`}
          >
            <div className={`
              flex items-center justify-center w-6 h-6 rounded-full shrink-0
              ${isCompleted ? 'bg-emerald-500/20 text-emerald-400' : ''}
              ${isActive ? 'bg-[#9C4A2A]/20 text-[#9C4A2A]' : ''}
              ${isPending ? 'bg-zinc-800 text-zinc-600' : ''}
            `}>
              {isCompleted ? (
                <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }}><TbCheck className="w-4 h-4" /></motion.div>
              ) : isActive ? (
                <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1.5, ease: "linear" }}>
                  <TbLoader2 className="w-4 h-4" />
                </motion.div>
              ) : (
                <span className="w-1.5 h-1.5 rounded-full bg-zinc-600" />
              )}
            </div>
            
            <div className="flex-1">
              <p className={`text-sm font-medium transition-colors ${
                isCompleted ? 'text-zinc-300' : isActive ? 'text-zinc-100' : 'text-zinc-500'
              }`}>
                {stage.name}
              </p>
              {isActive && (
                <motion.div 
                  className="h-0.5 bg-[#9C4A2A] mt-2 rounded-full origin-left"
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: 1 }}
                  transition={{ duration: stage.durationMs / 1000, ease: "linear" }}
                />
              )}
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
