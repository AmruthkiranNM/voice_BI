import { motion } from 'framer-motion';
import { TbMessageChatbot, TbDatabase, TbCode, TbBrain, TbChartBar, TbFileDescription } from 'react-icons/tb';

const AGENTS = [
  { id: 'intent', name: 'Intent Agent', icon: TbMessageChatbot, stages: ['Understanding Question', 'Detecting Business Intent', 'Retrieving Conversation Memory'] },
  { id: 'schema', name: 'Schema Agent', icon: TbDatabase, stages: ['Analyzing Database Schema', 'Identifying Relevant Tables', 'Selecting Business Metrics'] },
  { id: 'sql', name: 'SQL Agent', icon: TbCode, stages: ['Generating Optimized SQL', 'Validating SQL Query', 'Executing Database Query'] },
  { id: 'insight', name: 'Insight Agent', icon: TbBrain, stages: ['Analyzing Returned Results', 'Detecting Trends', 'Generating Business Insights'] },
  { id: 'visual', name: 'Visual Agent', icon: TbChartBar, stages: ['Selecting Best Visualization', 'Preparing Charts'] },
  { id: 'summary', name: 'Summary Agent', icon: TbFileDescription, stages: ['Generating Executive Explanation', 'Finalizing Response'] },
];

export default function AgentCards({ activeStageName }) {
  // Determine active agent based on the active stage name
  const activeAgent = AGENTS.find(agent => agent.stages.includes(activeStageName))?.id;

  return (
    <div className="grid grid-cols-3 gap-3 w-full">
      {AGENTS.map((agent) => {
        const isActive = activeAgent === agent.id;
        const Icon = agent.icon;

        return (
          <motion.div
            key={agent.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className={`
              relative overflow-hidden rounded-xl p-3 border transition-all duration-500
              ${isActive 
                ? 'bg-zinc-800/80 border-[#9C4A2A]/50 shadow-[0_0_15px_rgba(156,74,42,0.2)]' 
                : 'bg-zinc-900/40 border-zinc-800/50 opacity-60'}
            `}
          >
            {isActive && (
              <motion.div 
                className="absolute inset-0 bg-gradient-to-tr from-[#9C4A2A]/10 to-transparent"
                animate={{ opacity: [0.5, 1, 0.5] }}
                transition={{ duration: 2, repeat: Infinity }}
              />
            )}
            
            <div className="relative z-10 flex flex-col items-center justify-center gap-2">
              <div className={`p-2 rounded-full ${isActive ? 'bg-[#9C4A2A]/20 text-[#9C4A2A]' : 'bg-zinc-800 text-zinc-500'}`}>
                <Icon className="w-5 h-5" />
              </div>
              <span className={`text-[10px] uppercase font-bold tracking-wider text-center ${isActive ? 'text-zinc-200' : 'text-zinc-500'}`}>
                {agent.name}
              </span>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
