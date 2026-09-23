ZAI:

- APIKey:(redacted - stored in ~/.pi/agent/auth.json zai-coding-cn.key)

- curl-example:
  
  ```  
  curl -X POST "https://open.bigmodel.cn/api/paas/v4/chat/completions" \
   -H "Content-Type: application/json" \
   -H "Authorization: Bearer your-api-key" \
   -d '{
   "model": "glm-5.3",
   "messages": [
   {
   "role": "system",
   "content": "你是一名资深的全栈软件工程师，擅长前端开发、后端架构设计以及现代 Web 技术栈"
   },
   {
   "role": "user",
   "content": "帮我设计并编写一个个人博客网站，包含首页、文章列表、文章详情页，使用 React + Node.js 技术栈"
   }
   ],
   "thinking": {
   "type": "enabled"
   },
   "max_tokens": 65536,
   "temperature": 1.0
   }'
  ```
  
  
