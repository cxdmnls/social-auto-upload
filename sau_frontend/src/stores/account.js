import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAccountStore = defineStore('account', () => {
  // 存储所有账号信息
  const accounts = ref([])
  
  // 平台类型映射
  const platformTypes = {
    1: '小红书',
    2: '视频号',
    3: '抖音',
    4: '快手',
    5: '哔哩哔哩'
  }
  
  // 设置账号列表
  const setAccounts = (accountsData) => {
    // 转换后端返回的数据格式为前端使用的格式
    accounts.value = accountsData.map(item => {
      const id = Array.isArray(item) ? item[0] : item.id
      const type = Array.isArray(item) ? item[1] : item.type
      const filePath = Array.isArray(item) ? item[2] : (item.filePath || item.cookie_path)
      const name = Array.isArray(item) ? item[3] : (item.name || item.userName)
      const rawStatus = Array.isArray(item) ? item[4] : item.status
      const status = rawStatus === '验证中'
        ? '验证中'
        : (rawStatus === 1 || rawStatus === '1' || rawStatus === '正常' ? '正常' : '异常')

      return {
        id,
        type,
        filePath,
        name,
        status,
        platform: platformTypes[String(type)] || platformTypes[type] || '未知',
        avatar: '/vite.svg' // 默认使用vite.svg作为头像
      }
    })
  }
  
  // 添加账号
  const addAccount = (account) => {
    accounts.value.push(account)
  }
  
  // 更新账号
  const updateAccount = (id, updatedAccount) => {
    const index = accounts.value.findIndex(acc => acc.id === id)
    if (index !== -1) {
      accounts.value[index] = { ...accounts.value[index], ...updatedAccount }
    }
  }
  
  // 删除账号
  const deleteAccount = (id) => {
    accounts.value = accounts.value.filter(acc => acc.id !== id)
  }
  
  // 根据平台获取账号
  const getAccountsByPlatform = (platform) => {
    return accounts.value.filter(acc => acc.platform === platform)
  }
  
  return {
    accounts,
    setAccounts,
    addAccount,
    updateAccount,
    deleteAccount,
    getAccountsByPlatform
  }
})
